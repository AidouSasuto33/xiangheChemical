# Django基础ORM管理
from django.db import models
from system.models import Workshop
# 表单基础模型
from .core import BaseProductionStep
# =========================================================
# 工艺第一步： CVN合成
# =========================================================
class CVNSynthesis(BaseProductionStep):
    """
    Step 1: CVN 合成
    逻辑：投入原料 -> 产出粗品 -> (部分用于精馏)
    """
    workshop = models.ForeignKey(Workshop, on_delete=models.PROTECT, related_name='cvn_synthesis', verbose_name="工单所属车间", default=1) # 1是CVN_SYN车间id
    # =========================================================
    # 1. 投入原料 (Input)
    # =========================================================
    raw_dcb = models.FloatField("投入-二氯丁烷(kg)", default=0, null=True, blank=True)
    input_recycled_dcb = models.FloatField("投入-回收二氯丁烷(kg/L)", default=0, help_text="套用回收溶剂", null=True, blank=True)
    raw_nacn = models.FloatField("投入-氰化钠(kg)", default=0, null=True, blank=True)
    raw_tbab = models.FloatField("投入-TBAB(kg)", default=0, null=True, blank=True)
    raw_alkali = models.FloatField("投入-液碱(kg)", default=0, null=True, blank=True)

    # =========================================================
    # 2. 产出与质检 (Output & QC)
    # =========================================================
    crude_weight = models.FloatField("产出-CVN粗品重量(kg)", default=0, help_text="物理称重", blank=True, null=True)

    # 库存核心字段：记录已被精馏工段领用了多少
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False, help_text="系统自动更新，不可手改")

    # 质检百分比
    content_cvn = models.FloatField("中控-CVN含量%", null=True, blank=True)
    content_dcb = models.FloatField("中控-DCB含量%", null=True, blank=True)
    content_adn = models.FloatField("中控-己二腈含量%", null=True, blank=True)

    test_time = models.DateTimeField("送检时间", null=True, blank=True)

    # =========================================================
    # 3. 回收 (Recovery)
    # =========================================================
    # 注：无需再填日期和批号，直接关联本批次
    recovered_dcb_amount = models.FloatField("回收-DCB数量(L)", default=0, help_text="单位：升", blank=True, null=True)
    recovered_dcb_purity = models.FloatField("回收-DCB纯度%", null=True, blank=True)

    # =========================================================
    # 4. 环保/排污 (Waste)
    # =========================================================
    waste_batches = models.IntegerField("破氰废水处理(批次/釜)", default=0, help_text="填整数，用于计算排污费", blank=True, null=True)

    class Meta(BaseProductionStep.Meta):
        verbose_name = "1-CVN合成"
        verbose_name_plural = verbose_name

    # --- 核心属性：剩余可用量 ---
    @property
    def remaining_weight(self):
        """批次里还剩多少粗蒸CVN"""
        return max(0, self.crude_weight - self.consumed_weight)

    @property
    def status_label(self):
        """
        批次生命周期状态 (针对 CVA粗品)
        """
        if self.crude_weight < 0:
            return "异常批次"

        if self.consumed_weight <= 0:
            return "🟢 全新待领"
        elif self.remaining_weight <= 0:
            return "⚫ 耗尽归档"
        else:
            return "🟡 部分领用"

    status_label.fget.short_description = "当前状态"
    status_label.fget.admin_order_field = 'consumed_weight'
    url_name_base = "cvn_synthesis_update" # 用于reverse帮助消息模块生成url

