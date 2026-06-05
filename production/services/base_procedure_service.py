import json
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Q, F

from core.constants import KettleState
from core.constants.procedure_status import ProcedureState, ProcedureAction
from production.models import Kettle
from production.services.partial.procedure_state_service import ProcedureStateService
from inventory.services.inventory_service import update_single_inventory, check_materials_availability
from production.utils.bom_utils import get_procedure_bom_info
from production.utils.qc_utils import validate_qc_sum_100
from production.utils.output_validator import validate_output_balance
from .partial.labor_record_service import LaborRecordService


class BaseProcedureService:
    """
    生产工艺 Service 基类 (模板方法模式)
    封装了投产与完工的标准骨架、双擎库存扣减逻辑以及底层安全防线校验。
    """
    # ==========================================
    # 子类必须/可覆盖的配置项 (Configuration)
    # ==========================================
    PROCEDURE_KEY = None  # 工艺标识，如 'cvnsynthesis', 'cvndistillation'

    # 前置工艺物料相关配置 (若该工艺需要用到多批次前置原料，则配置以下项)
    SOURCE_PROCEDURE_KEY = None  # 前置工艺标识，如 'cvnsynthesis' (新增：用于动态拉取前置质检字段)
    SOURCE_BATCH_MODEL = None  # 前置产物模型，如 CVNSynthesis
    SOURCE_CRUDE_WEIGHT_FIELD = None  # 前置模型的主产物字段名，用于 F 表达式过滤，如 'cvn_syn_crude_weight'
    INPUTS_RELATED_NAME = None  # 当前模型指向前置投料子表的 related_name
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

    # 新增：用于缓存前置工艺的质检字段，供多批次选择器使用
    SOURCE_QC_FIELDS = []
    SOURCE_QC_NAMES = []

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

        # 新增：如果配置了前置工艺，去 BOM 里把前置工艺的质检要求拉过来
        if cls.SOURCE_PROCEDURE_KEY:
            cls.SOURCE_QC_FIELDS = get_procedure_bom_info(cls.SOURCE_PROCEDURE_KEY, 'qc_fields', 'field')
            cls.SOURCE_QC_NAMES = get_procedure_bom_info(cls.SOURCE_PROCEDURE_KEY, 'qc_fields', 'name')

    # ==========================================
    # 核心公共接口 (Template Methods)
    # ==========================================
    @classmethod
    def handle_action(cls, instance, action, user):
        with transaction.atomic():

            # 1. 执行特定动作的副作用钩子（如扣库存、记录工时快照）
            if action == ProcedureAction.START_PRODUCTION:
                cls._process_start(instance, user)
            elif action == ProcedureAction.FINISH_PRODUCTION:
                cls._process_finish(instance, user)
            elif action == ProcedureAction.SUBMIT_QC:
                cls._submit_qc(instance, user)
            elif action == ProcedureAction.PAUSE_ABNORMAL_PRODUCTION:
                cls._report_abnormal(instance, user)
            elif action == ProcedureAction.RESUME_ABNORMAL_PRODUCTION:
                cls._resume_running(instance, user)
            elif action == ProcedureAction.CANCEL_PRODUCTION:
                cls._cancel_production(instance, user)

            # 2. 执行状态扭转
            ProcedureStateService.process_action(instance, action)


    @classmethod
    def _process_start(cls, instance, user):
        """标准投产流程：防守校验 -> 双擎库存扣减 -> 状态机接管"""
        if instance.status != ProcedureState.NEW:
            raise ValidationError(f"当前状态为 {instance.get_status_display()}，无法执行投产操作。")

        cls._execute_inventory_deduction(instance, user)

    @classmethod
    def _process_finish(cls, instance, user):
        """标准完工流程：防守校验 -> QC与平衡底线拦截 -> 产出入库 -> 状态机接管"""
        if instance.status not in [ProcedureState.RUNNING, ProcedureState.DELAYED]:
            raise ValidationError(f"当前状态为 {instance.get_status_display()}，无法执行完工操作。")

        # 1. 强制底线校验：转化为字典交由 Utils 验证
        data_dict = {field.name: getattr(instance, field.name) for field in instance._meta.fields}

        is_bal_valid, bal_msg = validate_output_balance(cls.PROCEDURE_KEY, data_dict)
        if not is_bal_valid:
            raise ValidationError(f"完工拦截 (平衡异常)：{bal_msg}")

        cls._execute_inventory_addition(instance, user)

    @classmethod
    def _submit_qc(cls, instance, user):
        # TODO要求上传质检照片
        if instance.status != ProcedureState.PENDING_QC:
            raise ValidationError(f"当前状态为 {instance.get_status_display()}，无法录入质检数据。")
        # 1. 强制底线校验：转化为字典交由 Utils 验证
        data_dict = {field.name: getattr(instance, field.name) for field in instance._meta.fields}
        is_qc_valid, qc_msg = validate_qc_sum_100(cls.PROCEDURE_KEY, data_dict)
        if not is_qc_valid:
            raise ValidationError(f"完工拦截 (质检异常)：{qc_msg}")


    @classmethod
    def _report_abnormal(cls, instance, user):
        # TODO 实现要求上传附件逻辑, 或可要求备注
        pass

    @classmethod
    def _resume_running(cls, instance, user):
        # 似乎无需做什么， 也许加个要求备注吧
        pass

    @classmethod
    def _mark_delayed(cls, instance, user):
        # TODO 自动对比预计时间与现在时间，如果超出预计时间则标记成delay状态
        # 似乎需要增加新的signal
        pass

    @classmethod
    def _cancel_production(cls, instance, user):
        # TODO 编写inventory 物料回滚逻辑并调用
        cls._execute_inventory_rollback(instance, user)
        pass
  
    @classmethod
    def get_production_context(cls, instance=None, require_source_batches=False):
        """为前端渲染提供工艺上下文 (利用内存级 BOM 缓存与前置可用批次)。"""
        context = {
            'inputs': cls.INPUT_FIELDS,
            'outputs': cls.OUTPUT_FIELDS,
            'qc_fields': cls.QC_FIELDS,
        }

        # 动态获取，如果存在才加入，服务于 cvn_dis 等含有精前质检的模型
        if cls.QC_PRE_FIELDS:
            context['qc_pre_fields'] = cls.QC_PRE_FIELDS

        # 新增：将前置质检字段字典传给前端，供 JS 动态渲染徽章和下拉列表
        if cls.SOURCE_QC_FIELDS:
            context['source_qc_info'] = json.dumps([
                {'field': f, 'name': n} for f, n in zip(cls.SOURCE_QC_FIELDS, cls.SOURCE_QC_NAMES)
            ])

        if require_source_batches or cls.SOURCE_BATCH_MODEL:
            context['available_source_batches'] = cls._get_available_source_batches_json(instance=instance)

        context['available_kettles'] = Kettle.objects.filter(status=KettleState.IDLE)
        context['cleaning_kettles'] = Kettle.objects.filter(status=KettleState.CLEANING)

        return context


    @classmethod
    def _execute_inventory_deduction(cls, instance, user):
        """双擎库存扣减引擎 (精简版：Form负责用户友好提示，Service在锁内行使终极防御)"""

        # 1. 辅料预检（由于基础辅料通常不走多批次悲观锁，可保留批量预检）
        material_requirements = []
        for field, name in zip(cls.INPUT_FIELDS, cls.INPUT_NAMES):
            if not field.startswith('input_total_'):
                qty = getattr(instance, field, 0)
                if qty and float(qty) > 0:
                    material_requirements.append((field, float(qty), name))

        if material_requirements:
            is_valid, mat_errors = check_materials_availability(material_requirements)
            if not is_valid:
                raise ValidationError("投产失败，基础物料库存不足：\n" + "\n".join(mat_errors))

        # 2. 执行扣减（在锁内同时进行终极防守与扣减）
        for field, name in zip(cls.INPUT_FIELDS, cls.INPUT_NAMES):

            # 引擎 B: 扣减前置批次
            if field.startswith('input_total_'):
                total_use_weight = 0
                inputs_qs = getattr(instance, cls.INPUTS_RELATED_NAME).all()

                for item in inputs_qs:
                    # 【核心锁内防御】：获取悲观锁，此时数据绝对安全可靠
                    source_batch = cls.SOURCE_BATCH_MODEL.objects.select_for_update().get(pk=item.source_batch_id)

                    # 终极底线拦截：防范高并发下的超领
                    if item.use_weight > source_batch.remaining_weight:
                        raise ValidationError(
                            f"【并发冲突拦截】前置批次 {source_batch.batch_no} 刚刚被其他工单占用，剩余额度不足！"
                            f"(需 {item.use_weight}kg, 实际仅剩 {source_batch.remaining_weight}kg)"
                        )

                    source_batch.consumed_weight += item.use_weight
                    source_batch.save(update_fields=['consumed_weight'])
                    total_use_weight += item.use_weight

                if total_use_weight > 0:
                    global_key = cls.SOURCE_GLOBAL_INVENTORY_KEY or field
                    cls._update_single_stock(global_key, 'production', -total_use_weight, f"{name}溯源扣减 - 单号: {instance.batch_no}", user)

            # 引擎 A: 直扣基础物料
            else:
                qty = getattr(instance, field, 0)
                if qty and float(qty) > 0:
                    cls._update_single_stock(field, 'production', -qty, f"投料: {name} - 单号: {instance.batch_no}", user)

    @classmethod
    def _execute_inventory_rollback(cls, procedure, user):
        bom_info = get_procedure_bom_info(cls.PROCEDURE_KEY)
        if not bom_info:
            return

        # 1. 归还原料
        for input_item in bom_info:

            if not input_item.startswith('input_total_'):
                consumed_amount = getattr(procedure, input_item, 0)
                if consumed_amount and consumed_amount > 0:
                    update_single_inventory(
                        user=user,
                        key=input_item,
                        change_amount=consumed_amount,
                        action_type='roll_back',
                        note=f"工单取消：{procedure.batch_no} 撤销投产，归还 {input_item}"
                    )

        # 2. 释放前置批次 & 领料明细清零 (方案 B)
        if hasattr(cls, 'INPUTS_RELATED_NAME') and cls.INPUTS_RELATED_NAME:
            inputs_manager = getattr(procedure, cls.INPUTS_RELATED_NAME, None)

            if inputs_manager:
                for batch_input in inputs_manager.all():
                    source_batch = batch_input.source_batch
                    consumed_in_this_procedure = batch_input.consumed_weight

                    if consumed_in_this_procedure and consumed_in_this_procedure > 0:
                        source_batch.consumed_weight -= consumed_in_this_procedure
                        source_batch.save()

                        batch_input.use_weight = 0
                        batch_input.save()

    @classmethod
    def _execute_inventory_addition(cls, instance, user):
        """产出入库引擎"""
        for field, name in zip(cls.OUTPUT_FIELDS, cls.OUTPUT_NAMES):
            qty = getattr(instance, field, 0)
            if qty and float(qty) > 0:
                cls._update_single_stock(field, qty, f"产出: {name} - 单号: {instance.batch_no}", user)

    @classmethod
    def _get_available_source_batches_json(cls, instance=None):
        """基于 F 表达式获取有结余的前置批次，动态嵌入前置质检数据"""
        if not cls.SOURCE_BATCH_MODEL or not cls.SOURCE_CRUDE_WEIGHT_FIELD:
            return "[]"

        # 基础查询：获取所有“有结余”的可用批次
        filter_cond = Q(**{f"{cls.SOURCE_CRUDE_WEIGHT_FIELD}__gt": F('consumed_weight')})

        # 【逻辑补完】：如果 instance 存在，把这个工单已经选中的批次也加进来
        if instance and instance.pk:
            selected_ids = getattr(instance, cls.INPUTS_RELATED_NAME).values_list('source_batch_id', flat=True)
            filter_cond |= Q(pk__in=selected_ids)

        # 执行查询
        available_batches = cls.SOURCE_BATCH_MODEL.objects.filter(
            filter_cond,
            status=ProcedureState.COMPLETED
        ).distinct().order_by('-id')

        batch_list = []
        for batch in available_batches:
            batch_data = {
                'batch_no': batch.batch_no,
                'remaining_weight': round(batch.remaining_weight, 2),
            }

            # 核心修改：动态遍历前置质检字段，彻底告别硬编码
            if cls.SOURCE_QC_FIELDS:
                for sqc_field in cls.SOURCE_QC_FIELDS:
                    # 使用 getattr 动态获取批次对象的质检值，不存在则默认为 0.0
                    batch_data[sqc_field] = getattr(batch, sqc_field, 0.0)

            batch_list.append(batch_data)

        return json.dumps(batch_list)

    @classmethod
    def _update_single_stock(cls, key, action_type, amount, note, user):
        """包装调用外部 inventory_service 避免在主流程中处理繁琐的报错拼接"""
        is_success = update_single_inventory(key=key, action_type=action_type, change_amount=amount , note=note, user=user)
        if not is_success:
            action_str = "增加" if amount > 0 else "扣减"
            raise ValueError(f"系统严重错误：物料 (Key: {key}) 尝试{action_str} {abs(amount)} 失败！操作已全部回滚！")