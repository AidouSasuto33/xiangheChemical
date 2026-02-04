# Django基础ORM管理
from django.db import models
# 引入 Postgres 特有的 ArrayField (虽然 JSONField 更通用，但这里用 JSON 兼容性更好)
from django.db.models import JSONField
# django用户管理库
from django.contrib.auth.models import User

from .kettle import Kettle

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
        # --- 质量/重量 (基准: kg) ---
        ('kg', '千克 (kg)'),
        ('ton', '吨 (Ton)'),  # 如果选了吨，代码层计算成本时需 * 1000
        # --- 体积 (基准: L) ---
        ('L', '升 (L)'),
        ('m3', '立方米 (m³)'),  # 污水处理常见单位
        # --- 计件/计时 ---
        ('batch', '批/釜 (Batch)'),
        ('hour', '小时 (Hour)'),
        ('piece', '件/个 (Piece)'),  # 比如买桶的费用
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
    
    STATUS_NEW = 'new'
    STATUS_RUNNING = 'running'
    STATUS_COMPLETED = 'completed'

    STATUS_CHOICES = [
        (STATUS_NEW, '新建/待投 (New)'),
        (STATUS_RUNNING, '生产中 (Running)'),
        (STATUS_COMPLETED, '已完工 (Completed)'),
    ]
    
    status = models.CharField(
        "状态",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_NEW,
        db_index=True,
        help_text="生产状态流转：新建 -> 生产中(锁原料) -> 完工(入成品)"
    )

    kettle = models.ForeignKey(
        Kettle,
        on_delete=models.PROTECT,
        related_name='%(class)s_related',
        verbose_name="生产设备",
        help_text="该生产步骤所使用的具体釜皿/设备",
        null=True,
        blank=True
    )

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
