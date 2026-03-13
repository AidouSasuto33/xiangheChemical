from django.db import models
from .core import BaseProductionStep
from .cva_synthesis import CVASynthesis
from core import constants
# =========================================================
# 工艺第四步： CVC合成
# =========================================================
class CVCSynthesis(BaseProductionStep):
    """
    Step 4: CVC 合成 (内销/普通级)
    逻辑：投入CVA粗品(Step 3) + 二氯亚砜 -> 氯化反应(多点中控) -> 精馏 -> CVC成品
    """
    # 投入
    input_total_cva_weight = models.FloatField("投入CVA总重(kg)", default=0)
    raw_socl2 = models.FloatField("投入-二氯亚砜(kg)", default=0)

    # 产出
    distillation_head_weight = models.FloatField("产出-前馏份/头酒(kg)", default=0, help_text="精馏初期的不合格部分")
    cvc_syn_crude_weight = models.FloatField("产出-CVC合格品重量(kg)", default=0)
    # 质检
    content_cvc = models.FloatField("成品-CVC含量%", null=True, blank=True, help_text="CVC合成的纯度")
    content_cva = models.FloatField("成品-CVA含量%", null=True, blank=True, help_text="CVC合成工艺中CVA的纯度")

    # 库存逻辑
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False)

    class Meta(BaseProductionStep.Meta):
        verbose_name = "4-CVC合成(内销)"
        verbose_name_plural = verbose_name

    @property
    def remaining_weight(self):
        return max(0, self.cvc_syn_crude_weight - self.consumed_weight)

    @property
    def status_label(self):
        if self.cvc_syn_crude_weight <= 0:
            return "异常批次"
        if self.consumed_weight <= 0:
            return "🟢 全新待领"
        elif self.remaining_weight <= 0:
            return "⚫ 耗尽归档"
        else:
            return "🟡 部分领用"

    status_label.fget.short_description = "当前状态"
    status_label.fget.admin_order_field = 'consumed_weight'


class CVCSynthesisInput(models.Model):
    """CVC合成 投料明细表 (取代原 input_cva_sources JSONField)"""
    synthesis = models.ForeignKey(
        'CVCSynthesis', on_delete=models.CASCADE, related_name='inputs', verbose_name="所属CVC合成工单"
    )
    source_batch = models.ForeignKey(
        'CVASynthesis', on_delete=models.PROTECT, related_name='consumed_in_cvc_nx', verbose_name="CVA粗品来源"
    )
    use_weight = models.FloatField("投入重量(kg)")

    snapshot_cva = models.FloatField("领用时CVA含量%", null=True, blank=True)

    class Meta:
        verbose_name = "CVC合成投入明细"
        verbose_name_plural = verbose_name
        unique_together = ('synthesis', 'source_batch')

    def __str__(self):
        return f"{self.synthesis.batch_no} <- {self.source_batch.batch_no} ({self.use_weight}kg)"


class CVCSynthesisIPCLog(models.Model):
    """合成过程监控记录表 (取代原 ipc_logs JSONField)"""
    synthesis = models.ForeignKey(
        'CVCSynthesis', on_delete=models.CASCADE, related_name='ipc_logs', verbose_name="所属工单"
    )
    log_time = models.DateTimeField("记录时间")
    duration_hours = models.FloatField("反应时长(h)", null=True, blank=True)
    ipc_cvc = models.FloatField("中控-CVC%", null=True, blank=True)
    ipc_cva = models.FloatField("中控-CVA%", null=True, blank=True)
    note = models.CharField("备注", max_length=255, blank=True)

    class Meta:
        verbose_name = "CVC合成中控记录"
        verbose_name_plural = verbose_name
        ordering = ['log_time']

    def __str__(self):
        return f"{self.synthesis.batch_no} IPC @ {self.log_time.strftime('%H:%M')}"