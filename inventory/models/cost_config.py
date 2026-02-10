from django.db import models

class CostConfig(models.Model):
    """
    系统配置核心表：存储原料单价、工人工资、排污费及产品售价等。
    """
    CATEGORY_CHOICES = [
        ('material', '原料成本'),
        ('labor', '人工成本'),
        ('waste', '环保/排污成本'),
        ('product', '产品/产值'),
    ]

    UNIT_CHOICES = [
        ('kg', '千克 (kg)'),
        ('ton', '吨 (Ton)'),
        ('L', '升 (L)'),
        ('m3', '立方米 (m³)'),
        ('batch', '批/釜'),
        ('hour', '小时 (Hour)'),
    ]

    key = models.CharField("配置代码", max_length=50, unique=True)
    label = models.CharField("配置项名称", max_length=50)
    category = models.CharField("费用类别", max_length=20, choices=CATEGORY_CHOICES)
    
    price = models.DecimalField("单价/金额 (元)", max_digits=10, decimal_places=2, default=0)
    unit = models.CharField("计价单位", max_length=20, choices=UNIT_CHOICES, default='kg')
    
    description = models.CharField("说明", max_length=200, blank=True)
    updated_at = models.DateTimeField("最近更新", auto_now=True)

    def __str__(self):
        return f"{self.label}: {self.price}元/{self.unit}"

    class Meta:
        verbose_name = "费用/价格配置"
        verbose_name_plural = verbose_name