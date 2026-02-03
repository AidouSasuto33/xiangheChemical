from django.db import models
from django.conf import settings  # 引用用户模型


class Inventory(models.Model):
    """
    实物库存表
    职责：只管数量 (Quantity)，不管单价。单价去 CostConfig 查。
    """
    CATEGORY_CHOICES = [
        ('raw', '原材料'),  # 二氯丁烷, 液碱...
        ('intermediate', '中间品'),  # CVN粗品, CVA粗品...
        ('product', '成品'),  # CVC合格品...
    ]

    # 单位
    UNIT_CHOICES = [
        ('kg', '千克 (kg)'),
        ('ton', '吨 (Ton)'),
        ('L', '升 (L)'),
        ('m3', '立方米 (m³)'),
        ('batch', '批/釜'),
        ('piece', '件/个'),
    ]
    unit = models.CharField(
        "计量单位",
        max_length=20,
        choices=UNIT_CHOICES,
        default='kg'
    )

    # 核心字段
    key = models.CharField("物料代码", max_length=50, unique=True, help_text="程序调用唯一标识，如 raw_dcb")
    name = models.CharField("物料名称", max_length=50)
    category = models.CharField("分类", max_length=20, choices=CATEGORY_CHOICES, default='raw')

    # 数量管理 (只存 kg)
    quantity = models.FloatField("当前库存(kg)", default=0)

    # 阈值 (可选功能)
    safe_stock = models.FloatField("安全库存警戒线", default=0, help_text="低于此数值前端标红")

    updated_at = models.DateTimeField("最后变动时间", auto_now=True)

    class Meta:
        verbose_name = "9-实时库存"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.name}: {self.quantity} kg"