import json
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F

from core.constants.procedure_status import ProcedureState, ProcedureAction
from production.services.partial.procedure_state_service import ProcedureStateService
from inventory.services.inventory_service import update_single_inventory
from production.utils.bom_utils import get_procedure_bom_info
from production.utils.qc_utils import validate_qc_sum_100
from production.utils.output_validator import validate_output_balance


class BaseProcedureService:
    """
    生产工艺 Service 基类 (模板方法模式)
    封装了投产与完工的标准骨架、双擎库存扣减逻辑以及底层安全防线校验。
    """
    # ==========================================
    # 子类必须/可覆盖的配置项 (Configuration)
    # ==========================================
    PROCEDURE_KEY = None                # 工艺标识，如 'cvnsynthesis', 'cvndistillation'

    # 前置工艺物料相关配置 (若该工艺需要用到多批次前置原料，则配置以下项)
    SOURCE_BATCH_MODEL = None           # 前置产物模型，如 CVNSynthesis
    SOURCE_CRUDE_WEIGHT_FIELD = None    # 前置模型的主产物字段名，用于 F 表达式过滤，如 'cvn_syn_crude_weight'
    INPUTS_RELATED_NAME = None          # 当前模型指向前置投料子表的 related_name
    SOURCE_GLOBAL_INVENTORY_KEY = None  # 对应的全局库存键名，防止 BOM 别名与库存键不匹配，如 'cvn_syn_crude_weight'

    # ==========================================
    # 自动生成的类变量 (子类加载时由基类自动绑定缓存)
    # ==========================================
    INPUT_FIELDS = []
    INPUT_NAMES = []
    OUTPUT_FIELDS = []
    OUTPUT_NAMES = []
    QC_FIELDS = []
    QC_PRE_FIELDS = []

    @classmethod
    def __init_subclass__(cls, **kwargs):
        """
        子类初始化钩子：当 Django 启动并加载继承此基类的子类时，仅执行一次。
        确保 BOM 配置被永久缓存在类变量中，彻底消灭运行时的重复解析性能损耗。
        """
        super().__init_subclass__(**kwargs)
        if cls.PROCEDURE_KEY:
            cls.INPUT_FIELDS = get_procedure_bom_info(cls.PROCEDURE_KEY, 'inputs', 'field')
            cls.INPUT_NAMES = get_procedure_bom_info(cls.PROCEDURE_KEY, 'inputs', 'name')
            cls.OUTPUT_FIELDS = get_procedure_bom_info(cls.PROCEDURE_KEY, 'outputs', 'field')
            cls.OUTPUT_NAMES = get_procedure_bom_info(cls.PROCEDURE_KEY, 'outputs', 'name')
            cls.QC_FIELDS = get_procedure_bom_info(cls.PROCEDURE_KEY, 'qc_fields', 'field')
            cls.QC_PRE_FIELDS = get_procedure_bom_info(cls.PROCEDURE_KEY, 'qc_pre_fields', 'field')

    # ==========================================
    # 核心公共接口 (Template Methods)
    # ==========================================
    @classmethod
    def process_start(cls, instance, user):
        """标准投产流程：防守校验 -> 双擎扣减 -> 状态机接管"""
        if instance.status != ProcedureState.NEW:
            raise ValidationError(f"当前状态为 {instance.get_status_display()}，无法执行投产操作。")

        with transaction.atomic():
            # 1. 执行双擎库存扣减 (辅料直扣 + 前置批次溯源扣减)
            cls._execute_inventory_deduction(instance, user)

            ProcedureStateService.process_action(instance, ProcedureAction.START_PRODUCTION, user=user)

    @classmethod
    def process_finish(cls, instance, user):
        """标准完工流程：防守校验 -> QC与平衡底线拦截 -> 产出入库 -> 状态机接管"""
        if instance.status not in [ProcedureState.RUNNING, ProcedureState.DELAYED]:
            raise ValidationError(f"当前状态为 {instance.get_status_display()}，无法执行完工操作。")

        # 1. 强制底线校验：转化为字典交由 Utils 验证
        data_dict = {field.name: getattr(instance, field.name) for field in instance._meta.fields}

        is_qc_valid, qc_msg = validate_qc_sum_100(cls.PROCEDURE_KEY, data_dict)
        if not is_qc_valid:
            raise ValidationError(f"完工拦截 (质检异常)：{qc_msg}")

        is_bal_valid, bal_msg = validate_output_balance(cls.PROCEDURE_KEY, data_dict)
        if not is_bal_valid:
            raise ValidationError(f"完工拦截 (平衡异常)：{bal_msg}")

        with transaction.atomic():
            # 2. 执行产出物料自动入库
            cls._execute_inventory_addition(instance, user)

            ProcedureStateService.process_action(instance, ProcedureAction.FINISH_PRODUCTION, user=user)

    @classmethod
    def get_production_context(cls, require_source_batches=False):
        """为前端渲染提供工艺上下文 (利用内存级 BOM 缓存与前置可用批次)。"""
        context = {
            'inputs': cls.INPUT_FIELDS,
            'outputs': cls.OUTPUT_FIELDS,
            'qc_fields': cls.QC_FIELDS,
        }

        # 动态获取，如果存在才加入，服务于 cvn_dis 等含有精前质检的模型
        if cls.QC_PRE_FIELDS:
            context['qc_pre_fields'] = cls.QC_PRE_FIELDS

        if require_source_batches or cls.SOURCE_BATCH_MODEL:
            context['available_source_batches'] = cls._get_available_source_batches_json()

        return context

    # ==========================================
    # 内部引擎与钩子 (Hooks & Engines)
    # ==========================================
    @classmethod
    def _execute_inventory_deduction(cls, instance, user):
        """双擎库存扣减引擎"""
        for field, name in zip(cls.INPUT_FIELDS, cls.INPUT_NAMES):
            # 引擎 B: 前置多批次溯源扣减规则 (约定以 'input_total_' 开头)
            if field.startswith('input_total_'):
                if not cls.SOURCE_BATCH_MODEL:
                    raise ValidationError(f"系统配置错误：物料 {name} 触发了前置批次溯源逻辑，但未配置 SOURCE_BATCH_MODEL。")

                total_use_weight = 0
                inputs_qs = getattr(instance, cls.INPUTS_RELATED_NAME).all()

                if not inputs_qs.exists():
                    raise ValidationError(f"未找到 {name} 投入明细，无法投产。")

                for item in inputs_qs:
                    # 加锁防并发超领
                    source_batch = cls.SOURCE_BATCH_MODEL.objects.select_for_update().get(pk=item.source_batch_id)
                    if item.use_weight > source_batch.remaining_weight:
                        raise ValidationError(
                            f"并发冲突：前置批次 {source_batch.batch_no} 剩余可用量不足！"
                            f"试图领用 {item.use_weight}kg，当前仅剩 {source_batch.remaining_weight}kg。"
                        )
                    source_batch.consumed_weight += item.use_weight
                    source_batch.save(update_fields=['consumed_weight'])
                    total_use_weight += item.use_weight

                # 同步扣减全局代表该前置产物总量的库存
                if total_use_weight > 0:
                    # 优先使用配置的真实全局库存键，若未配置则降级使用 BOM 字段名
                    global_key = cls.SOURCE_GLOBAL_INVENTORY_KEY or field
                    cls._update_single_stock(global_key, -total_use_weight, f"{name}溯源扣减 - 单号: {instance.batch_no}", user)

            # 引擎 A: 标准辅料全局直扣规则
            else:
                qty = getattr(instance, field, 0)
                if qty and float(qty) > 0:
                    cls._update_single_stock(field, -qty, f"投料: {name} - 单号: {instance.batch_no}", user)

    @classmethod
    def _execute_inventory_addition(cls, instance, user):
        """产出入库引擎"""
        for field, name in zip(cls.OUTPUT_FIELDS, cls.OUTPUT_NAMES):
            qty = getattr(instance, field, 0)
            if qty and float(qty) > 0:
                cls._update_single_stock(field, qty, f"产出: {name} - 单号: {instance.batch_no}", user)

    @classmethod
    def _get_available_source_batches_json(cls):
        """基于 F 表达式获取有结余的前置批次"""
        if not cls.SOURCE_BATCH_MODEL or not cls.SOURCE_CRUDE_WEIGHT_FIELD:
            return "[]"

        # 动态组装 F 表达式过滤条件
        filter_kwargs = {
            f"{cls.SOURCE_CRUDE_WEIGHT_FIELD}__gt": F('consumed_weight')
        }

        available_batches = cls.SOURCE_BATCH_MODEL.objects.filter(
            status=ProcedureState.COMPLETED,
            **filter_kwargs
        ).order_by('end_time')

        batch_list = []
        for batch in available_batches:
            batch_data = {
                'batch_no': batch.batch_no,
                'remaining_weight': round(batch.remaining_weight, 2),
            }
            # 为 CVN 精馏保留特殊的含量下发逻辑，保持基类整洁，子类纯净
            if cls.PROCEDURE_KEY == 'cvndistillation':
                batch_data.update({
                    'cvn': getattr(batch, 'content_cvn', 0.0),
                    'dcb': getattr(batch, 'content_dcb', 0.0),
                    'adn': getattr(batch, 'content_adn', 0.0),
                })
            # 如果未来 CVA 合成也需要额外信息，继续增加 elif 即可
            batch_list.append(batch_data)

        return json.dumps(batch_list)

    @classmethod
    def _update_single_stock(cls, key, amount, note, user):
        """包装调用外部 inventory_service 避免在主流程中处理繁琐的报错拼接"""
        is_success = update_single_inventory(key=key, change_amount=amount, note=note, user=user)
        if not is_success:
            action_str = "增加" if amount > 0 else "扣减"
            raise ValueError(f"系统严重错误：物料 (Key: {key}) 尝试{action_str} {abs(amount)} 失败！操作已全部回滚！")