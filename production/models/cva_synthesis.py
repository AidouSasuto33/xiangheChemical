from django.db import models, transaction
from django.db.models import JSONField, F
from django.core.exceptions import ValidationError

from .core import BaseProductionStep
# 引入CVN 精馏模型
from .cvn_distillation import CVNDistillation
from ..utils.batch_generator import generate_batch_number


# =========================================================
# 工艺第三步： CVA合成
# =========================================================
class CVASynthesis(BaseProductionStep):
    """
    Step 3: CVA 合成及脱水
    逻辑：投入CVN精品(Step 2) + 酸碱 -> 反应 -> 脱水 -> CVA粗品
    """

    # =========================================================
    # 1. 投入 (Input)
    # =========================================================
    # 来源：Step 2 (CVN 精馏)
    input_sources = JSONField(
        "投入CVN精品来源",
        default=list,
        help_text="""
        结构：[{
            "batch_no": "CVN-JING-2026...", 
            "use_weight": 200, 
            "content_cvn": 99.5, 
            "note": "..."
        }]
        """
    )

    input_total_weight = models.FloatField("投入CVN精品总重(kg)", default=0)

    # 辅料
    raw_hcl = models.FloatField("投入-盐酸(kg)", default=0)
    raw_alkali = models.FloatField("投入-液碱(kg)", default=0)

    # =========================================================
    # 2. 产出 (Output) - CVA 粗品 (脱水后)
    # =========================================================
    crude_weight = models.FloatField("产出-CVA粗品重量(kg)", default=0, help_text="脱水后的实际称重")

    # 库存核心：Step 4 (CVC合成) 将从这里领料
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False)

    # =========================================================
    # 3. 质检 (QC)
    # =========================================================
    content_cva = models.FloatField("中控-CVA含量%", null=True, blank=True)
    content_cvn = models.FloatField("中控-CVN残留%", null=True, blank=True, help_text="标准应 < 0.5%")
    content_water = models.FloatField("中控-水分%", null=True, blank=True, help_text="脱水效果指标")

    class Meta(BaseProductionStep.Meta):
        verbose_name = "3-CVA合成"
        verbose_name_plural = verbose_name

    # --- 核心属性：剩余可用量 (供 Step 4 使用) ---
    @property
    def remaining_weight(self):
        return max(0, self.crude_weight - self.consumed_weight)

    # --- 校验逻辑 ---
    def clean(self):
        super().clean()

        calculated_total = 0

        # 获取旧对象用于库存回滚计算
        old_instance = None
        if self.pk:
            try:
                old_instance = CVASynthesis.objects.get(pk=self.pk)
            except CVASynthesis.DoesNotExist:
                pass

        for item in self.input_sources:
            batch_no = item.get('batch_no')
            try:
                use_weight = float(item.get('use_weight', 0))
            except (ValueError, TypeError):
                raise ValidationError(f"批号 {batch_no} 重量格式错误")

            if use_weight <= 0:
                raise ValidationError("投入重量必须大于0")

            calculated_total += use_weight

            # 1. 查找源头 (Step 2)
            try:
                source_batch = CVNDistillation.objects.get(batch_no=batch_no)
            except CVNDistillation.DoesNotExist:
                raise ValidationError(f"CVN精品批号 {batch_no} 不存在")

            # 2. 计算库存可用量
            recoverable = 0
            if old_instance:
                for old_item in old_instance.input_sources:
                    if old_item.get('batch_no') == batch_no:
                        recoverable = float(old_item.get('use_weight', 0))
                        break

            # 注意：这里调用的是 source_batch (Step 2) 的 remaining_weight
            # 如果没在 CVNDistillation 加这个属性，这里会报错
            if hasattr(source_batch, 'remaining_weight'):
                max_allowable = source_batch.remaining_weight + recoverable
                if use_weight > max_allowable:
                    raise ValidationError(f"批号 {batch_no} 库存不足。可用: {max_allowable}kg")
            else:
                # 临时容错，防止代码直接崩（建议开发时去掉此 else）
                pass

        if abs(self.input_total_weight - calculated_total) > 0.1:
            raise ValidationError("投入CVN总重与明细不符")

    # --- 保存逻辑 (扣减 Step 2 库存) ---
    @transaction.atomic
    def save(self, *args, **kwargs):
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVASynthesis, "CVA")

        # 1. 归还旧库存
        if self.pk:
            old_instance = CVASynthesis.objects.get(pk=self.pk)
            for item in old_instance.input_sources:
                CVNDistillation.objects.filter(batch_no=item.get('batch_no')).update(
                    consumed_weight=models.F('consumed_weight') - float(item.get('use_weight', 0))
                )

        # 2. 扣减新库存
        for item in self.input_sources:
            CVNDistillation.objects.filter(batch_no=item.get('batch_no')).update(
                consumed_weight=models.F('consumed_weight') + float(item.get('use_weight', 0))
            )

        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        # 归还库存
        for item in self.input_sources:
            CVNDistillation.objects.filter(batch_no=item.get('batch_no')).update(
                consumed_weight=models.F('consumed_weight') - float(item.get('use_weight', 0))
            )
        super().delete(*args, **kwargs)