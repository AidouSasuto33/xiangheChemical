# Django基础ORM管理
from django.db import models
from system.models import Workshop
# 引入基础模型
from .core import BaseProductionStep
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
    # 虽然可以通过子表 inputs 算加权平均，但工厂可能有实测值，故保留字段
    pre_content_cvn = models.FloatField("精前-CVN含量%", null=True, blank=True)
    pre_content_dcb = models.FloatField("精前-DCB含量%", null=True, blank=True)
    pre_content_adn = models.FloatField("精前-己二腈含量%", null=True, blank=True)

    # =========================================================
    # 3. 产出 (Output)
    # =========================================================
    crude_weight = models.FloatField("产出-CVN精品重量(kg)", default=0)
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
        return max(0, self.crude_weight - self.consumed_weight)

    @property
    def dry_weight_pre(self):
        """精前折干重量(kg) = 投入总重量 * 精前CVN含量"""
        if self.input_total_cvn_weight and self.pre_content_cvn:
            return self.input_total_cvn_weight * (self.pre_content_cvn / 100.0)
        return 0.0


    @property
    def status_label(self):
        """
        批次生命周期状态 (针对 CVN精品)
        """
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



    class Meta(BaseProductionStep.Meta):
        verbose_name = "2-CVN精馏"
        verbose_name_plural = verbose_name

    url_name_base = "cvn_distillation_update"  # 用于reverse帮助消息模块生成url


class CVNDistillationInput(models.Model):
    """
    精馏投料明细表 (多对一关联，取代原 JSONField)
    """
    # 1. 归属哪个精馏工单？
    distillation = models.ForeignKey(
        'CVNDistillation',
        on_delete=models.CASCADE,
        related_name='inputs',
        verbose_name="所属精馏工单"
    )

    # 2. 扣减的是哪个合成粗品？
    source_batch = models.ForeignKey(
        'CVNSynthesis',
        on_delete=models.PROTECT,  # 核心防御：被领用的粗品绝不能被物理删除
        related_name='consumed_in_distillations',
        verbose_name="粗品来源"
    )

    # 3. 扣了多少？
    use_weight = models.FloatField("投入重量(kg)")

    # 4. (可选) 历史快照
    # 为了防止几年后 CVNSynthesis 的含量数据被修改导致追溯对不上，
    # 我们可以在领料瞬间，把当时的含量复制一份存入这里作为“快照”。
    snapshot_cvn = models.FloatField("领用时CVN含量%", null=True, blank=True)
    snapshot_dcb = models.FloatField("领用时DCB含量%", null=True, blank=True)
    snapshot_adn = models.FloatField("领用时己二腈含量%", null=True, blank=True)



    def __str__(self):
        return f"{self.distillation.batch_no} <- {self.source_batch.batch_no} ({self.use_weight}kg)"

    class Meta:
        verbose_name = "精馏投入明细"
        verbose_name_plural = verbose_name
        # 联合约束：同一个精馏单里，不能添加两次同一个粗品批号
        unique_together = ('distillation', 'source_batch')

