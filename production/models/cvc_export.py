from django.db import models
from .core import BaseProductionStep
from .cvc_synthesis import CVCSynthesis


# =========================================================
# 工艺第五步： CVC外销精制
# =========================================================
class CVCExport(BaseProductionStep):
    """
    Step 5: CVC 外销精制 (Wai Xiao)
    逻辑：投入CVC合格品(Step 4) -> 二次精馏 -> CVC精品
    """
    # 投入
    input_total_cvc_weight = models.FloatField("投入总重量(kg)", default=0)
    # 产出
    cvc_dis_crude_weight = models.FloatField("产出-CVC精品重量(kg)", default=0, help_text="二次蒸馏后的实际装桶重量")
    # 质检
    content_cvc = models.FloatField("精品-CVC含量%", null=True, blank=True)
    content_cva = models.FloatField("精品-CVA含量%", null=True, blank=True)
    # 库存
    consumed_weight = models.FloatField("已发货重量(kg)", default=0, editable=False)

    class Meta:
        verbose_name = "5-CVC外销精制"
        verbose_name_plural = verbose_name

    @property
    def remaining_weight(self):
        return max(0, self.cvc_dis_crude_weight - self.consumed_weight)

    @property
    def status_label(self):
        if self.cvc_dis_crude_weight <= 0:
            return "异常批次"
        if self.consumed_weight <= 0:
            return "🟢 全新待售"
        elif self.remaining_weight <= 0:
            return "⚫ 售罄发毕"
        else:
            return "🟡 部分发货"

    status_label.fget.short_description = "当前状态"
    status_label.fget.admin_order_field = 'consumed_weight'


class CVCExportInput(models.Model):
    """CVC外销精制 投料明细表 (取代原 JSONField)"""
    export = models.ForeignKey(
        'CVCExport', on_delete=models.CASCADE, related_name='inputs', verbose_name="所属外销精制工单"
    )
    source_batch = models.ForeignKey(
        'CVCSynthesis', on_delete=models.PROTECT, related_name='consumed_in_cvc_wx', verbose_name="CVC合格品来源"
    )
    use_weight = models.FloatField("投入重量(kg)")

    snapshot_cvc = models.FloatField("领用时CVC含量%", null=True, blank=True)

    class Meta:
        verbose_name = "外销精制投入明细"
        verbose_name_plural = verbose_name
        unique_together = ('export', 'source_batch')

    def __str__(self):
        return f"{self.export.batch_no} <- {self.source_batch.batch_no} ({self.use_weight}kg)"