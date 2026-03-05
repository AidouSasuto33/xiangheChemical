from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from django.db.models import F

from production.models.core import BaseProductionStep
from production.models.cvn_distillation import CVNDistillation
from production.models.cvn_synthesis import CVNSynthesis
from production.models.kettle import Kettle

import json


# 如果有库存全局服务，预留导入位置
# from inventory.services.inventory_service import inventory_service


def process_start(instance: CVNDistillation, user):
    """
    执行投产逻辑 (Status: New -> Running)
    核心动作：
    1. 锁定并扣减前置粗品 (CVNSynthesis) 的可用库存。
    2. 变更当前工单状态和开始时间。
    3. 占用物理釜皿。
    """
    if instance.status != BaseProductionStep.STATUS_NEW:
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

        # 2. 变更工单状态
        instance.status = BaseProductionStep.STATUS_RUNNING
        instance.start_time = timezone.now()

        # 记录操作日志/更新人（如果 BaseProductionStep 中有对应字段）
        # instance.updated_by = user

        instance.save(update_fields=['status', 'start_time'])

        # 3. 占用釜皿
        if instance.kettle:
            instance.kettle.status = Kettle.STATUS_RUNNING
            instance.kettle.save(update_fields=['status'])


def process_finish(instance: CVNDistillation, user):
    """
    执行完工逻辑 (Status: Running -> Completed)
    核心动作：
    1. 校验产出与釜残是否已填写。
    2. 变更当前工单状态和结束时间。
    3. 释放物理釜皿（转入清洗状态）。
    4. [可选] 将精品 CVN 推送至全局库存总表。
    """
    if instance.status != BaseProductionStep.STATUS_RUNNING:
        raise ValidationError(f"当前状态为 {instance.get_status_display()}，无法执行完工操作。")

    # 防御性校验：确保产出重量已录入
    if not instance.output_weight or instance.output_weight <= 0:
        raise ValidationError("完工失败：尚未录入有效的精品产出重量。")

    with transaction.atomic():
        # 1. 变更工单状态
        instance.status = BaseProductionStep.STATUS_COMPLETED
        instance.end_time = timezone.now()
        instance.save(update_fields=['status', 'end_time'])

        # 2. 释放釜皿转入清洗
        if instance.kettle:
            instance.kettle.status = Kettle.STATUS_CLEANING
            instance.kettle.save(update_fields=['status'])


def get_available_synthesis_batches_json():
    """
    获取所有可用的 CVN 合成粗品批次，打包为 JSON DTO 供前端交互使用。
    条件：状态为已完工 (completed)，且剩余可用量 > 0 (产出 > 已领用)
    """
    # 核心优化：利用 Django F 表达式在数据库引擎层面直接过滤有结余的批次
    available_batches = CVNSynthesis.objects.filter(
        status=BaseProductionStep.STATUS_COMPLETED,
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