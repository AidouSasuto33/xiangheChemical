from django.db import models
from .core import BaseProductionStep, BaseMultiBatchInput
from .cvn_distillation import CVNDistillation
from system.models import Workshop
# =========================================================
# 工艺第三步： CVA合成
# =========================================================
class CVASynthesis(BaseProductionStep):
    """
    Step 3: CVA 合成及脱水
    逻辑：投入CVN精品(Step 2) + 酸碱 -> 反应 -> 脱水 -> CVA粗品
    """
    workshop = models.ForeignKey(Workshop, on_delete=models.PROTECT, related_name='cva_synthesis',
                                 verbose_name="工单所属车间", default=3)  # 3是cva_syn车间id
    # 投入
    input_total_cvc_dis_weight = models.FloatField("投入CVN精品总重(kg)", default=0)
    # 辅料
    raw_hcl = models.FloatField("投入-盐酸(kg)", default=0)
    raw_alkali = models.FloatField("投入-液碱(kg)", default=0)
    # 产出
    cva_crude_weight = models.FloatField("产出-CVA粗品重量(kg)", default=0, help_text="脱水后的实际称重")
    # 库存核心
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False)
    # 新增：精前质检 (动态加权平均写入)
    pre_content_cvn = models.FloatField("精前-CVN含量%", null=True, blank=True)
    pre_content_dcb = models.FloatField("精前-DCB含量%", null=True, blank=True)
    pre_content_adn = models.FloatField("精前-ADN含量%", null=True, blank=True)
    # 质检 (QC)
    content_cva = models.FloatField("中控-CVA含量%", null=True, blank=True)
    content_cvn = models.FloatField("中控-CVN残留%", null=True, blank=True, help_text="标准应 < 0.5%")
    content_water = models.FloatField("中控-水分%", null=True, blank=True, help_text="脱水效果指标")

    class Meta(BaseProductionStep.Meta):
        verbose_name = "3-CVA合成"
        verbose_name_plural = verbose_name

    @property
    def remaining_weight(self):
        """剩余可用量 (供 Step 4 使用)"""
        return max(0, self.cva_crude_weight - self.consumed_weight)

    @property
    def status_label(self):
        if self.cva_crude_weight < 0:
            return "异常批次"
        if self.consumed_weight <= 0:
            return "🟢 全新待领"
        elif self.remaining_weight <= 0:
            return "⚫ 耗尽归档"
        else:
            return "🟡 部分领用"

    status_label.fget.short_description = "当前状态"
    status_label.fget.admin_order_field = 'consumed_weight'
    url_name_base = "cva_synthesis_update"  # 用于reverse帮助消息模块生成url


class CVASynthesisInput(BaseMultiBatchInput):
    # 关联主表
    cva_synthesis = models.ForeignKey(
        'CVASynthesis',
        on_delete=models.CASCADE,
        related_name='inputs',
        verbose_name="所属CVA合成工单"
    )

    # 关联来源批次 (具体关联哪个模型在子类定义)
    source_batch = models.ForeignKey(
        'CVNDistillation',
        on_delete=models.PROTECT,
        related_name='consumed_in_cva_synthesis',
        verbose_name="CVN精品来源批次"
    )

    def __str__(self):
        return f"{self.cva_synthesis.batch_no} <- {self.source_batch.batch_no} ({self.use_weight}kg)"

    class Meta:
        verbose_name = "精馏投入明细"
        verbose_name_plural = verbose_name
        # 联合约束：同一个精馏单里，不能添加两次同一个粗品批号
        unique_together = ('cva_synthesis', 'source_batch')