from django.db import models
# 引入 Postgres 特有的 ArrayField (虽然 JSONField 更通用，但这里用 JSON 兼容性更好)
# 既然确定用 PG，我们直接用 Django 标准 JSONField，它在 PG 上表现完美
from django.db.models import JSONField
# django用户管理库
from django.contrib.auth.models import User
# 批号生成器
from .utils.batch_generator import generate_batch_number


import datetime

# ==========================================
# 0. 费用配置 (CostConfig)
# ==========================================

class CostConfig(models.Model):
    """
    系统配置核心表：存储原料单价、工人工资、排污费及产品售价等。
    设计原则：Key-Value 模式，Key 给程序看，Label 给用户看。
    """

    # --- 1. 类别常量定义 ---
    CATEGORY_CHOICES = [
        ('material', '原料成本'),
        ('labor', '人工成本'),
        ('waste', '环保/排污成本'),
        ('product', '产品/产值'),  # 新增：用于设定成品基准价或外销价
    ]

    # --- 2. 单位常量定义 ---
    UNIT_CHOICES = [
        ('kg', '千克 (kg)'),
        ('ton', '吨 (Ton)'),
        ('L', '升 (L)'),
        ('batch', '批次/次 (Batch)'),
        ('person_time', '人/小时 (Person/Time)'),  # 专门用于计件工资
    ]

    # --- 3. 字段定义 ---
    key = models.CharField(
        "配置代码 (Key)",
        max_length=50,
        unique=True,
        help_text="【禁止修改】程序调用的唯一标识，例如：price_dcb, wage_input"
    )

    label = models.CharField(
        "显示名称 (Label)",
        max_length=50,
        help_text="在页面上显示的名称，例如：二氯丁烷单价"
    )

    category = models.CharField(
        "费用类别",
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='material'
    )

    price = models.DecimalField(
        "单价/金额 (元)",
        max_digits=10,
        decimal_places=2,
        default=0
    )

    unit = models.CharField(
        "计量单位",
        max_length=20,
        choices=UNIT_CHOICES,
        default='kg'
    )

    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        verbose_name = "0-费用及价格配置"
        verbose_name_plural = verbose_name
        ordering = ['category', 'key']

    def __str__(self):
        # 显示格式：[原料] 二氯丁烷: 12.50元/kg
        return f"[{self.get_category_display()}] {self.label}: {self.price}元/{self.get_unit_display()}"


# ==========================================
# 1. 抽象基类 (BaseProductionStep) - 重构版
# ==========================================

class BaseProductionStep(models.Model):
    """
    生产工段基类 (Abstract)
    核心逻辑变更：
    1. 时间：由单一 Date 改为 Start/End 手动选择。
    2. 劳务：废弃固定字段，改用 JSON 灵活存储 "工种+人数+单位量"。
    3. 灵活性：允许部分步骤为空。
    """

    # --- 1. 核心追踪 ---
    batch_no = models.CharField("生产批号", max_length=50, unique=True)
    kettles = JSONField("使用釜号列表", default=list, help_text="支持多选，如 ['R101', 'R102']")

    # --- 2. 时间管理 ---
    # 不使用 auto_now，完全由文员手动选择日历
    start_time = models.DateTimeField("开始时间")
    end_time = models.DateTimeField("结束时间")

    # --- 3. 劳务成本记录 (核心变更) ---
    # 数据结构示例：
    # [
    #   {"role_key": "wage_input", "count": 2, "amount": 1.5, "note": "投料"},
    #   {"role_key": "wage_waste", "count": 1, "amount": 1.0, "note": "废水处理"}
    # ]
    labor_records = JSONField(
        "人工工时记录",
        default=list,
        blank=True,
        help_text="格式：[{工种Key, 人数, 耗时/次数}]"
    )

    # --- 4. 辅助信息 ---
    operator = models.ForeignKey(
        User,
        on_delete=models.PROTECT,  # 关键：如果该账号有数据，禁止物理删除，强迫管理员改用“禁用”
        verbose_name="记录员",
        help_text="自动关联当前登录账号，不可为空"
    )
    remarks = models.TextField("备注", blank=True, null=True)

    # 系统自动记录的修改时间（用于审计，不用于业务）
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("最后更新", auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.batch_no} ({self.start_time.strftime('%Y-%m-%d')})"

    @property
    def duration_hours(self):
        """辅助计算：总耗时（小时）"""
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            return round(delta.total_seconds() / 3600, 1)
        return 0

# Step 1: CVN 合成
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
