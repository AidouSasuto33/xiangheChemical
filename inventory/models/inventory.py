from django.db import models
from django.conf import settings

class Inventory(models.Model):
    """
    实物库存表
    职责：只管数量 (Quantity)，不管单价。单价去 CostConfig 查。
    """
    CATEGORY_CHOICES = [
        ('raw', '原材料'),
        ('intermediate', '中间品'),
        ('product', '成品'),
    ]

    UNIT_CHOICES = [
        ('kg', '千克 (kg)'),
        ('ton', '吨 (Ton)'),
        ('L', '升 (L)'),
        ('m3', '立方米 (m³)'),
        ('batch', '批/釜'),
        ('piece', '件/个'),
    ]

    unit = models.CharField("计量单位", max_length=20, choices=UNIT_CHOICES, default='kg')
    key = models.CharField("物料代码", max_length=50, unique=True, help_text="程序调用唯一标识，如 raw_dcb")
    name = models.CharField("物料名称", max_length=50)
    category = models.CharField("分类", max_length=20, choices=CATEGORY_CHOICES, default='raw')

    # 库存核心
    quantity = models.FloatField("当前库存", default=0)
    safe_stock = models.FloatField("安全库存预警线", default=0, help_text="低于此数值时标红预警")

    def __str__(self):
        return f"{self.name} ({self.quantity} {self.unit})"

    class Meta:
        verbose_name = "库存清单"
        verbose_name_plural = verbose_name
        ordering = ['category', 'key']