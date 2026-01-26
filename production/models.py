from django.db import models


# ==========================================
# 0. 抽象基类 (Code Assist 的好点子 + 真实业务字段)
# ==========================================
class BaseProductionStep(models.Model):
    """
    所有生产工段共有的字段，避免重复编写。
    """
    date = models.DateField("生产日期")
    batch_no = models.CharField("生产批号", max_length=50, unique=True, help_text="唯一标识，用于后续工段追踪")
    kettle_no = models.CharField("釜号", max_length=20, blank=True)
    operator = models.CharField("操作员", max_length=50, blank=True, default="文员")

    created_at = models.DateTimeField("录入时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        abstract = True  # 告诉 Django 这不是一张表，只是个模板
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - {self.batch_no}"


# ==========================================
# 1. 系统配置表 (用于灵活计算成本)
# ==========================================
class CostConfig(models.Model):
    """
    存储原料单价、工人工资、排污费等。
    """
    name = models.CharField("费用项名称", max_length=50, unique=True, help_text="例如：二氯丁烷单价")
    price = models.DecimalField("单价 (元)", max_digits=10, decimal_places=2, default=0)
    unit = models.CharField("单位", max_length=20, help_text="例如：kg, 吨, 批次")

    class Meta:
        verbose_name = "0-费用配置"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.name}: {self.price}/{self.unit}"


# ==========================================
# 2. 具体工段 (基于 Excel 真实列设计)
# ==========================================

# Step 1: CVN 合成
class CVNSynthesis(BaseProductionStep):
    # --- 原料投入 ---
    raw_dcb = models.FloatField("工业二氯丁烷 (kg)", default=0)
    raw_nacn = models.FloatField("液体氰化钠 (kg)", default=0)
    raw_tbab = models.FloatField("TBAB (kg)", default=0)
    raw_alkali = models.FloatField("液碱 (kg)", default=0)

    # --- 产出 ---
    crude_weight = models.FloatField("CVN粗品重量 (kg)", null=True, blank=True)
    content_cvn = models.FloatField("CVN中控含量%", null=True, blank=True)

    # --- 环保/成本项 ---
    waste_treatment = models.BooleanField("是否破氰废水处理", default=False)
    recovered_dcb = models.FloatField("回收DCB (L)", default=0)

    class Meta(BaseProductionStep.Meta):
        verbose_name = "1-CVN合成"
        verbose_name_plural = verbose_name


# Step 2: CVN 精馏
class CVNDistillation(BaseProductionStep):
    # --- 来源 ---
    input_source_batch = models.CharField("投粗蒸品批号", max_length=100)
    input_weight = models.FloatField("投入粗品重量 (kg)", default=0)

    # --- 产出 ---
    output_weight = models.FloatField("CVN精品产量 (kg)", default=0)
    residue_weight = models.FloatField("釜残重量 (kg)", default=0, help_text="危废，需计算处理成本")

    class Meta(BaseProductionStep.Meta):
        verbose_name = "2-CVN精馏"
        verbose_name_plural = verbose_name


# Step 3: CVA 合成
class CVASynthesis(BaseProductionStep):
    # --- 原料 ---
    input_cvn_batch = models.CharField("CVN精品批号", max_length=100)
    input_cvn_weight = models.FloatField("投入CVN精品重量 (kg)", default=0)
    raw_hcl = models.FloatField("盐酸重量 (kg)", default=0)
    raw_alkali = models.FloatField("液碱用量 (kg)", default=0)

    # --- 产出 ---
    output_weight = models.FloatField("CVA粗品重量 (kg)", default=0)
    result_cva = models.FloatField("CVA含量%", null=True, blank=True)

    class Meta(BaseProductionStep.Meta):
        verbose_name = "3-CVA合成"
        verbose_name_plural = verbose_name


# Step 4: CVC 合成及精馏
class CVCSynthesis(BaseProductionStep):
    # --- 原料 ---
    input_cva_weight = models.FloatField("CVA粗品重量 (kg)", default=0)
    raw_soCl2 = models.FloatField("二氯亚砜重量 (kg)", default=0)

    # --- 产出 ---
    output_qualified_weight = models.FloatField("CVC合格品重量 (kg)", default=0)
    output_premium_weight = models.FloatField("外销精品重量 (kg)", default=0, null=True, blank=True)

    # --- 废料 ---
    front_cut_weight = models.FloatField("前馏份重量 (kg)", default=0)

    class Meta(BaseProductionStep.Meta):
        verbose_name = "4-CVC合成"
        verbose_name_plural = verbose_name