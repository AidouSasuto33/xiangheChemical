from django.db import models
from .core import BaseProductionStep
from .cvn_distillation import CVNDistillation
from core import constants


# =========================================================
# 工艺第三步： CVA合成
# =========================================================
class CVASynthesis(BaseProductionStep):
    """
    Step 3: CVA 合成及脱水
    逻辑：投入CVN精品(Step 2) + 酸碱 -> 反应 -> 脱水 -> CVA粗品
    """
    input_total_weight = models.FloatField("投入CVN精品总重(kg)", default=0)

    # 辅料
    raw_hcl = models.FloatField("投入-盐酸(kg)", default=0)
    raw_alkali = models.FloatField("投入-液碱(kg)", default=0)

    # 产出
    crude_weight = models.FloatField("产出-CVA粗品重量(kg)", default=0, help_text="脱水后的实际称重")

    # 库存核心
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False)

    # 质检 (QC)
    content_cva = models.FloatField("中控-CVA含量%", null=True, blank=True)
    content_cvn = models.FloatField("中控-CVN残留%", null=True, blank=True, help_text="标准应 < 0.5%")
    content_water = models.FloatField("中控-水分%", null=True, blank=True, help_text="脱水效果指标")

    INVENTORY_MAPPING = {
        'raw_hcl': constants.KEY_RAW_HCL,
        'raw_alkali': constants.KEY_RAW_ALKALI,
        'crude_weight': constants.KEY_INTER_CVA_CRUDE,
    }

    class Meta(BaseProductionStep.Meta):
        verbose_name = "3-CVA合成"
        verbose_name_plural = verbose_name

    @property
    def remaining_weight(self):
        """剩余可用量 (供 Step 4 使用)"""
        return max(0, self.crude_weight - self.consumed_weight)

    @property
    def status_label(self):
        if self.crude_weight <= 0:
            return "异常批次"
        if self.consumed_weight <= 0:
            return "🟢 全新待领"
        elif self.remaining_weight <= 0:
            return "⚫ 耗尽归档"
        else:
            return "🟡 部分领用"

    status_label.fget.short_description = "当前状态"
    status_label.fget.admin_order_field = 'consumed_weight'


class CVASynthesisInput(models.Model):
    """CVA合成 投料明细表 (取代原 JSONField)"""
    synthesis = models.ForeignKey(
        'CVASynthesis',
        on_delete=models.CASCADE,
        related_name='inputs',
        verbose_name="所属CVA合成工单"
    )
    source_batch = models.ForeignKey(
        'CVNDistillation',
        on_delete=models.PROTECT,
        related_name='consumed_in_cva',
        verbose_name="CVN精品来源"
    )
    use_weight = models.FloatField("投入重量(kg)")

    # 快照字段
    snapshot_cvn = models.FloatField("领用时CVN含量%", null=True, blank=True)
    snapshot_dcb = models.FloatField("领用时DCB含量%", null=True, blank=True)
    snapshot_adn = models.FloatField("领用时己二腈含量%", null=True, blank=True)

    class Meta:
        verbose_name = "CVA合成投入明细"
        verbose_name_plural = verbose_name
        unique_together = ('synthesis', 'source_batch')

    def __str__(self):
        return f"{self.synthesis.batch_no} <- {self.source_batch.batch_no} ({self.use_weight}kg)"