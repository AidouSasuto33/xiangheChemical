# Django基础ORM管理
from django.db import models
from system.models import Workshop
# 引入基础模型
from .core import BaseProductionStep, BaseMultiBatchInput
# 引入 CVN 合成模型
from .cvn_synthesis import CVNSynthesis
# =========================================================
# 工艺第二步： CVN精馏
# =========================================================
class CVNDistillation(BaseProductionStep):
    """
    Step 2: CVN 精馏
    核心逻辑：多批次领料 -> 混合精馏 -> 产出精品 + 釜残
    """

    workshop = models.ForeignKey(Workshop, on_delete=models.PROTECT, related_name='cvn_distillation', verbose_name="工单所属车间", default=2) # 2是cvn_dis车间id
    # 投入cvn粗品批次
    input_total_cvn_weight = models.FloatField("投入总重量(kg)", default=0, help_text="应等于来源明细重量之和")

    # =========================================================
    # 2. 精馏前组份 (Pre-Distillation Composition)
    # =========================================================
    # 通过子表 inputs 算加权平均
    pre_content_cvn = models.FloatField("精前-CVN含量%", null=True, blank=True)
    pre_content_dcb = models.FloatField("精前-DCB含量%", null=True, blank=True)
    pre_content_adn = models.FloatField("精前-己二腈含量%", null=True, blank=True)

    # =========================================================
    # 3. 产出 (Output)
    # =========================================================
    cvn_dis_crude_weight = models.FloatField("产出-CVN精品重量(kg)", default=0)
    # 质检
    output_content_cvn = models.FloatField("精品-CVN含量%", null=True, blank=True)
    output_content_dcb = models.FloatField("精品-DCB含量%", null=True, blank=True)
    output_content_adn = models.FloatField("精品-己二腈含量%", null=True, blank=True)

    # 库存核心字段：记录已被CVA合成工段领用了多少
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False, help_text="系统自动更新，不可手改")

    # =========================================================
    # 4. 固废 (Waste)
    # =========================================================
    residue_weight = models.FloatField("釜残重量(kg)", default=0, help_text="危废处理成本依据")

    # --- 核心属性：剩余可用量 ---
    @property
    def remaining_weight(self):
        """批次里还剩多少精馏CVM"""
        return max(0, self.cvn_dis_crude_weight - self.consumed_weight)


    @property
    def status_label(self):
        """
        批次生命周期状态 (针对 CVN精品)
        """
        if self.cvn_dis_crude_weight <= 0:
            return "异常批次"

        if self.consumed_weight <= 0:
            return "🟢 全新待领"
        elif self.remaining_weight <= 0:
            return "⚫ 耗尽归档"
        else:
            return "🟡 部分领用"

    status_label.fget.short_description = "当前状态"
    status_label.fget.admin_order_field = 'consumed_weight'
    url_name_base = "cvn_distillation_update"  # 用于reverse帮助消息模块生成url


    class Meta(BaseProductionStep.Meta):
        verbose_name = "2-CVN精馏"
        verbose_name_plural = verbose_name


class CVNDistillationInput(BaseMultiBatchInput):
        # 关联主表
        distillation = models.ForeignKey(
            'CVNDistillation',
            on_delete=models.CASCADE,
            related_name='inputs',
            verbose_name="所属精馏工单"
        )

        # 关联来源批次 (具体关联哪个模型在子类定义)
        source_batch = models.ForeignKey(
            'CVNSynthesis',
            on_delete=models.PROTECT,
            related_name='consumed_in_distillation',
            verbose_name="粗品来源批次"
        )

        def __str__(self):
            return f"{self.distillation.batch_no} <- {self.source_batch.batch_no} ({self.use_weight}kg)"

        class Meta:
            verbose_name = "精馏投入明细"
            verbose_name_plural = verbose_name
            # 联合约束：同一个精馏单里，不能添加两次同一个粗品批号
            unique_together = ('distillation', 'source_batch')


