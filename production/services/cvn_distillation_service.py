from django.db import transaction
from django.utils import timezone
from django.core.exceptions import ValidationError

from production.models.core import BaseProductionStep
from production.models.cvn_distillation import CVNDistillation
from production.models.cvn_synthesis import CVNSynthesis
from production.models.kettle import Kettle


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
            # 假设 Kettle 模型中 STATUS_IN_USE 代表生产中
            instance.kettle.status = Kettle.STATUS_IN_USE
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

        # 3. 对接全局库存大盘 (预留扩展点)
        # 如果你的架构中使用了 inventory 子应用统一管理总账，可在此处调用：
        # inventory_service.add_stock(
        #     material_code=instance.INVENTORY_MAPPING.get('output_weight'),
        #     weight=instance.output_weight,
        #     batch_no=instance.batch_no,
        #     source_doc=f"CVN精馏入库",
        #     operator=user
        # )