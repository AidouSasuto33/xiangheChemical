# Django基础ORM管理
from django.db import models
# 表单基础模型
from .core import BaseProductionStep
# 批号生成器
from ..utils.batch_generator import generate_batch_number


# =========================================================
# 工艺第一步： CVN合成
# =========================================================
class CVNSynthesis(BaseProductionStep):
    """
    Step 1: CVN 合成
    逻辑：投入原料 -> 产出粗品 -> (部分用于精馏)
    """

    # =========================================================
    # 1. 投入原料 (Input)
    # =========================================================
    raw_dcb = models.FloatField("投入-二氯丁烷(kg)", default=0)
    raw_nacn = models.FloatField("投入-氰化钠(kg)", default=0)
    raw_tbab = models.FloatField("投入-TBAB(kg)", default=0)
    raw_alkali = models.FloatField("投入-液碱(kg)", default=0)

    # =========================================================
    # 2. 产出与质检 (Output & QC)
    # =========================================================
    crude_weight = models.FloatField("产出-CVN粗品重量(kg)", default=0, help_text="物理称重")

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
    recovered_dcb_amount = models.FloatField("回收-DCB数量(L)", default=0, help_text="单位：升")
    recovered_dcb_purity = models.FloatField("回收-DCB纯度%", null=True, blank=True)

    # =========================================================
    # 4. 环保/排污 (Waste)
    # =========================================================
    waste_batches = models.IntegerField("破氰废水处理(批次/釜)", default=0, help_text="填整数，用于计算排污费")

    class Meta(BaseProductionStep.Meta):
        verbose_name = "1-CVN合成"
        verbose_name_plural = verbose_name

    # --- 核心属性：剩余可用量 ---
    @property
    def remaining_weight(self):
        """仓库里还剩多少没被精馏用掉"""
        return max(0, self.crude_weight - self.consumed_weight)

    # --- 核心逻辑：自动生成批号 ---
    def save(self, *args, **kwargs):
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVNSynthesis, "CVN-CU")
        super().save(*args, **kwargs)
