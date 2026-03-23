from django.db import models
from .core import BaseProductionStep, BaseMultiBatchInput
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
    # 新增：精前质检 (动态加权平均写入)
    pre_content_cva = models.FloatField("精前-CVA含量%", null=True, blank=True)
    pre_content_cvn = models.FloatField("精前-CVN残留%", null=True, blank=True)
    pre_content_water = models.FloatField("精前-水分%", null=True, blank=True)
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
    url_name_base = "cvc_synthesis_update"  # 用于reverse帮助消息模块生成url


class CVCSynthesisInput(BaseMultiBatchInput):
    # 关联主表
    cvc_synthesis = models.ForeignKey(
        'CVCSynthesis',
        on_delete=models.CASCADE,
        related_name='inputs',
        verbose_name="所属CVA合成工单"
    )

    # 关联来源批次 (具体关联哪个模型在子类定义)
    source_batch = models.ForeignKey(
        'CVASynthesis',
        on_delete=models.PROTECT,
        related_name='consumed_in_cvc_synthesis',
        verbose_name="CVA来源批次"
    )

    def __str__(self):
        return f"{self.cvc_synthesis.batch_no} <- {self.source_batch.batch_no} ({self.use_weight}kg)"

    class Meta:
        verbose_name = "精馏投入明细"
        verbose_name_plural = verbose_name
        # 联合约束：同一个精馏单里，不能添加两次同一个粗品批号
        unique_together = ('cvc_synthesis', 'source_batch')