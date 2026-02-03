from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError


class Kettle(models.Model):
    """
    釜皿/设备资源表 (Master Data)
    用于管理车间的反应釜、精馏塔等核心设备
    """

    # === 状态常量 ===
    STATUS_IDLE = 'idle'
    STATUS_RUNNING = 'running'
    STATUS_CLEANING = 'to_clean'
    STATUS_MAINTENANCE = 'maintenance'

    STATUS_CHOICES = [
        (STATUS_IDLE, '🟢 空闲 (可使用)'),
        (STATUS_RUNNING, '🔴 生产中'),
        (STATUS_CLEANING, '🟡 待清洁'),
        (STATUS_MAINTENANCE, '⚪ 维护/故障'),
    ]

    # === 工艺选项 (用于 ArrayField) ===
    PROCESS_CHOICES = [
        ('cvn_syn', 'CVN 合成'),
        ('cvn_dist', 'CVN 精馏'),
        ('cva_syn', 'CVA 合成'),
        ('cvc_syn', 'CVC 合成'),
        ('cvc_dist', 'CVC 精馏'),
    ]

    # === 基础字段 ===
    name = models.CharField("釜皿编号", max_length=50, unique=True, help_text="例: 101, 2-05, R-01")
    workshop = models.CharField("所属车间", max_length=50, blank=True, help_text="例: 一车间, 二车间")
    capacity = models.FloatField("最大容积 (L)", default=0, help_text="单位: 升")
    current_level = models.FloatField("当前投入量", default=0, help_text="当前釜内物料总量，用于计算负载率")

    # === 核心能力 ===
    # 使用 Postgres ArrayField 实现多选
    # 在 Admin 里会显示为逗号分隔的输入，或者我们可以自定义 Widget
    supported_processes = ArrayField(
        models.CharField(max_length=20, choices=PROCESS_CHOICES),
        verbose_name="适用工艺",
        default=list,
        blank=True,
        help_text="该设备能做哪些工艺 (可多选)"
    )

    # === 动态状态 ===
    status = models.CharField("当前状态", max_length=20, choices=STATUS_CHOICES, default=STATUS_IDLE)

    # 预留字段：当前正在生产的批次号 (暂存字符串，未来可关联 Order)
    current_batch_no = models.CharField("当前占用批次", max_length=50, blank=True, null=True)

    # === 历史记录 (用于连投判断) ===
    last_process = models.CharField(
        "上批工艺",
        max_length=20,
        choices=PROCESS_CHOICES,
        null=True,
        blank=True,
        help_text="记录该设备上一次生产的工艺类型，用于判断连投或交叉污染风险"
    )

    last_product_name = models.CharField(
        "上批产品名称",
        max_length=100,
        null=True,
        blank=True,
        help_text="记录上一次生产的具体产品名称或代码"
    )

    class Meta:
        verbose_name = "釜皿/设备"
        verbose_name_plural = "釜皿/设备管理"
        ordering = ['workshop', 'name']

    def __str__(self):
        return f"[{self.workshop}] {self.name} ({self.get_status_display()})"

    def clean(self):
        super().clean()
        if self.current_level > self.capacity:
            raise ValidationError({'current_level': f"当前投入量 ({self.current_level}) 不能超过最大容积 ({self.capacity})"})

    @property
    def fill_percentage(self):
        if self.capacity > 0:
            return round((self.current_level / self.capacity) * 100)
        return 0
