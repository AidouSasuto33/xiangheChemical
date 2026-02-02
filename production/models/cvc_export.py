from django.db import models, transaction
from django.db.models import JSONField, F
from django.core.exceptions import ValidationError

from .core import BaseProductionStep
# 引入 Step 4 (CVC 内销) 作为原料来源
from .cvc_synthesis import CVCSynthesis
from ..utils.batch_generator import generate_batch_number


# =========================================================
# 工艺第五步： CVC外销精制
# =========================================================
class CVCExport(BaseProductionStep):
    """
    Step 5: CVC 外销精制 (Wai Xiao)
    逻辑：投入CVC合格品(Step 4) -> 二次精馏 -> CVC精品
    """

    # =========================================================
    # 1. 投入 (Input)
    # =========================================================
    # 来源：Step 4 (CVC 内销合格品)
    input_cvc_sources = JSONField(
        "投入CVC合格品来源",
        default=list,
        help_text="""
        结构：[{
            "batch_no": "CVC-NX-2026...", 
            "use_weight": 1000, 
            "content_cvc": 99.1, 
            "note": "..."
        }]
        """
    )

    input_total_weight = models.FloatField("投入总重量(kg)", default=0)

    # =========================================================
    # 2. 产出 (Output) - 精品
    # =========================================================
    # 这是一个物理称重值，肯定会比投入总重量少（因为有损耗）
    premium_weight = models.FloatField("产出-CVC精品重量(kg)", default=0, help_text="二次蒸馏后的实际装桶重量")

    # =========================================================
    # 3. 精品检测 (Premium QC)
    # =========================================================
    product_content_cvc = models.FloatField("精品-CVC含量%", null=True, blank=True)
    product_content_cva = models.FloatField("精品-CVA含量%", null=True, blank=True)

    # =========================================================
    # 4. 库存 (Inventory)
    # =========================================================
    # 如果系统还要管销售发货，这个字段依然需要
    consumed_weight = models.FloatField("已领用/发货重量(kg)", default=0, editable=False)

    class Meta(BaseProductionStep.Meta):
        verbose_name = "5-CVC外销精制"
        verbose_name_plural = verbose_name

    # --- 核心属性 ---
    @property
    def remaining_weight(self):
        return max(0, self.premium_weight - self.consumed_weight)

    def clean(self):
        super().clean()

        calculated_total = 0
        old_instance = None
        if self.pk:
            try:
                old_instance = CVCExport.objects.get(pk=self.pk)
            except CVCExport.DoesNotExist:
                pass

        # 校验 CVC 合格品来源
        for item in self.input_cvc_sources:
            batch_no = item.get('batch_no')
            try:
                use_weight = float(item.get('use_weight', 0))
            except (ValueError, TypeError):
                raise ValidationError(f"批号 {batch_no} 重量格式错误")

            if use_weight <= 0:
                raise ValidationError("投入重量必须大于0")

            calculated_total += use_weight

            # 1. 查找源头 (Step 4)
            try:
                source_batch = CVCSynthesis.objects.get(batch_no=batch_no)
            except CVCSynthesis.DoesNotExist:
                raise ValidationError(f"CVC内销批号 {batch_no} 不存在")

            # 2. 计算库存可用量
            recoverable = 0
            if old_instance:
                for old_item in old_instance.input_cvc_sources:
                    if old_item.get('batch_no') == batch_no:
                        recoverable = float(old_item.get('use_weight', 0))
                        break

            # 确保 Step 4 有 remaining_weight 属性
            if hasattr(source_batch, 'remaining_weight'):
                max_allowable = source_batch.remaining_weight + recoverable
                if use_weight > max_allowable:
                    raise ValidationError(f"批号 {batch_no} 库存不足。可用: {max_allowable}kg")

        if abs(self.input_total_weight - calculated_total) > 0.1:
            raise ValidationError("投入总重与明细不符")

        # 逻辑校验：产出不能大于投入（物理定律）
        if self.premium_weight > self.input_total_weight:
            # 除非有极其特殊的情况，否则精馏不可能变重
            # 用于确保文员填错警告
            raise ValidationError("产出精品重量不能大于投入重量")

    @transaction.atomic
    def save(self, *args, **kwargs):
        # 批号生成：CVC-WX (外销/Wai Xiao)
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVCExport, "CVC-WX")

        # 1. 归还 Step 4 旧库存
        if self.pk:
            old_instance = CVCExport.objects.get(pk=self.pk)
            for item in old_instance.input_cvc_sources:
                CVCSynthesis.objects.filter(batch_no=item.get('batch_no')).update(
                    consumed_weight=models.F('consumed_weight') - float(item.get('use_weight', 0))
                )

        # 2. 扣减 Step 4 新库存
        for item in self.input_cvc_sources:
            CVCSynthesis.objects.filter(batch_no=item.get('batch_no')).update(
                consumed_weight=models.F('consumed_weight') + float(item.get('use_weight', 0))
            )

        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        # 归还 Step 4 库存
        for item in self.input_cvc_sources:
            CVCSynthesis.objects.filter(batch_no=item.get('batch_no')).update(
                consumed_weight=models.F('consumed_weight') - float(item.get('use_weight', 0))
            )
        super().delete(*args, **kwargs)