# production/models/cvn_stripping_form.py
from django.db import models
from .core import BaseProductionStep, BaseMultiBatchInput
from .cvn_synthesis import CVNSynthesis


# =========================================================
# 工艺新增步： CVN粗蒸 (CVN Stripping)
# =========================================================
class CVNStripping(BaseProductionStep):
    """
    CVN 粗蒸
    核心逻辑：合成液领料 -> 粗蒸 -> 产出粗蒸粗品 + 回收DCB
    """
    default_workshop_code = 'CVN_STR'

    # =========================================================
    # 1. 投入 (Input)
    # =========================================================
    input_total_cvn_weight = models.FloatField("CVN合成液重量(kg)", default=0, help_text="应等于来源明细重量之和")

    # =========================================================
    # 2. 粗蒸前组份 (Pre-Stripping Composition / 合成液)
    # =========================================================
    pre_content_cvn = models.FloatField("合成液-CVN含量%", null=True, blank=True)
    pre_content_dcb = models.FloatField("合成液-DCB含量%", null=True, blank=True)
    pre_content_adn = models.FloatField("合成液-ADN含量%", null=True, blank=True)

    # =========================================================
    # 3. 产出 (Output)
    # =========================================================
    cvn_str_crude_weight = models.FloatField("CVN粗蒸粗品重量(kg)", null=True, blank=True)
    recycled_dcb = models.FloatField("回收DCB重量(kg)", null=True, blank=True)

    # =========================================================
    # 4. 质检结果 (QC / 粗蒸后)
    # =========================================================
    output_content_cvn = models.FloatField("粗蒸-CVN含量%", null=True, blank=True)
    output_content_dcb = models.FloatField("粗蒸-DCB含量%", null=True, blank=True)
    output_content_adn = models.FloatField("粗蒸-ADN含量%", null=True, blank=True)
    recycled_dcb_purity=  models.FloatField("粗蒸工序回收DCB纯度%", default=0, null=True, blank=True)

    @property
    def remaining_weight(self):
        """
        剩余可领用的粗蒸粗品重量
        """
        if self.cvn_str_crude_weight is None:
            return 0
        return round(self.cvn_str_crude_weight - self.consumed_weight, 2)

    @property
    def status_label(self):
        """
        批次生命周期状态 (CVN粗品)
        """
        if self.cvn_dis_crude_weight < 0:
            return "异常批次"

        if self.consumed_weight <= 0:
            return "🟢 全新待领"
        elif self.remaining_weight <= 0:
            return "⚫ 耗尽归档"
        else:
            return "🟡 部分领用"

    status_label.fget.short_description = "当前状态"
    status_label.fget.admin_order_field = 'consumed_weight'
    url_name_base = "cvn_stripping_update"  # 用于reverse帮助消息模块生成url

    class Meta(BaseProductionStep.Meta):
        verbose_name = "2-CVN粗蒸"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.batch_id} - CVN粗蒸"


# =========================================================
# 领料子表：CVN粗蒸投料明细
# =========================================================
class CVNStrippingInput(BaseMultiBatchInput):
    """
    CVN 粗蒸的投料明细（多对一：多个合成批次投入一个粗蒸批次）
    """
    # 关联主表
    stripping = models.ForeignKey(
        'CVNStripping',
        on_delete=models.CASCADE,
        related_name='inputs',
        verbose_name="所属粗蒸工单"
    )

    # 关联来源批次 (来源于 CVN 合成)
    source_batch = models.ForeignKey(
        'CVNSynthesis',
        on_delete=models.PROTECT,
        related_name='consumed_in_stripping',
        verbose_name="来源合成批次"
    )

    class Meta:
        verbose_name = "CVN粗蒸投料明细"
        verbose_name_plural = verbose_name