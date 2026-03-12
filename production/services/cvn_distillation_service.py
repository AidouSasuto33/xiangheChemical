import json
from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models import F

from production.models.cvn_distillation import CVNDistillation
from production.models.cvn_synthesis import CVNSynthesis
# 引入最新的状态机常量和 Service
from core.constants.procedure_status import ProcedureState, ProcedureAction
from production.services.partial.procedure_state_service import ProcedureStateService


def process_start(instance: CVNDistillation, user):
    """
    执行投产逻辑 (Status: New -> Running)
    核心动作：
    1. 锁定并扣减前置粗品 (CVNSynthesis) 的可用库存。
    2. 调用状态机服务变更状态并联动占用物理釜皿。
    """
    if instance.status != ProcedureState.NEW:
        raise ValidationError(f"当前状态为 {instance.get_status_display()}，无法执行投产操作。")

    with transaction.atomic():
        # 1. 遍历并扣减子表中的粗品库存
        inputs = instance.inputs.all()
        if not inputs.exists():
            raise ValidationError("未找到粗正品投入明细，无法投产。")

        for item in inputs:
            # 重新从数据库获取最新的 source_batch（使用 select_for_update 加锁防并发）
            source_batch = CVNSynthesis.objects.select_for_update().get(pk=item.source_batch_id)

            # 核心防御：防止超领（虽然在 Form 中校验过，但 Service 层必须有最终底线）
            if item.use_weight > source_batch.remaining_weight:
                raise ValidationError(
                    f"并发冲突：粗品批次 {source_batch.batch_no} 剩余可用量不足！"
                    f"试图领用 {item.use_weight}kg，当前仅剩 {source_batch.remaining_weight}kg。"
                )

            # 扣减库存（累加已领用量）
            source_batch.consumed_weight += item.use_weight
            source_batch.save(update_fields=['consumed_weight'])

        # 2. 更新时间并调用状态机流转 (原有的改变状态和占用釜皿的逻辑，已全部交由状态机接管)
        if not instance.start_time:
            instance.start_time = timezone.now()

        ProcedureStateService.process_action(instance, ProcedureAction.START_PRODUCTION, user=user)


def process_finish(instance: CVNDistillation, user):
    """
    执行完工逻辑 (Status: Running -> Completed)
    核心动作：
    1. 校验产出与釜残是否已填写。
    2. 调用状态机服务变更状态并联动释放物理釜皿（转入清洗状态）。
    3. [可选] 将精品 CVN 推送至全局库存总表。
    """
    # 允许从进行中或者延迟状态完工
    if instance.status not in [ProcedureState.RUNNING, ProcedureState.DELAYED]:
        raise ValidationError(f"当前状态为 {instance.get_status_display()}，无法执行完工操作。")

    # 防御性校验：确保产出重量已录入
    if not instance.crude_weight or instance.crude_weight <= 0:
        raise ValidationError("完工失败：尚未录入有效的精品产出重量。")

    with transaction.atomic():
        # 这里如果以后有向全局库存服务 (inventory_service) 增加精品的逻辑，请写在这里
        # ...

        # 更新时间并调用状态机流转 (状态变更及釜皿释放均已封装)
        if not instance.end_time:
            instance.end_time = timezone.now()

        ProcedureStateService.process_action(instance, ProcedureAction.FINISH_PRODUCTION, user=user)


def get_available_synthesis_batches_json():
    """
    获取所有可用的 CVN 合成粗品批次，打包为 JSON DTO 供前端交互使用。
    条件：状态为已完工 (completed)，且剩余可用量 > 0 (产出 > 已领用)
    """
    # 核心优化：利用 Django F 表达式在数据库引擎层面直接过滤有结余的批次
    # 将旧的 BaseProductionStep.STATUS_COMPLETED 替换为 ProcedureState.COMPLETED
    available_batches = CVNSynthesis.objects.filter(
        status=ProcedureState.COMPLETED,
        crude_weight__gt=F('consumed_weight')
    ).order_by('end_time')  # 按照完工时间排序，先进先出 (FIFO) 提示

    batch_list = []
    for batch in available_batches:
        batch_list.append({
            'batch_no': batch.batch_no,
            # 直接调用模型的 property，确保业务逻辑的一致性
            'remaining_weight': round(batch.remaining_weight, 2),
            # 兼容化验单可能未填全的情况，赋予默认值 0.0
            'cvn': batch.content_cvn or 0.0,
            'dcb': batch.content_dcb or 0.0,
            'adn': batch.content_adn or 0.0,
        })

    # 将 Python 字典列表转化为 JSON 字符串，防止前端解析时遇到单引号等语法错误
    return json.dumps(batch_list)