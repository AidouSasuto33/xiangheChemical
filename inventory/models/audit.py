from django.db import models
from django.conf import settings
# 修改引用：指向同目录下的 inventory 和 cost_config
from inventory.models import Inventory
from inventory.models import CostConfig

class InventoryLog(models.Model):
    """
    库存变动流水账
    """
    ACTION_CHOICES = [
        ('purchase', '购入/入库'),
        ('sale', '销售/出库'),
        ('correction', '盘点/修正'),
        ('production', '生产消耗/产出'),
        ('safe_stock', '预警线调整'), # 补上之前新增的类型
    ]

    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, verbose_name="关联物料")
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="操作人"
    )
    action_type = models.CharField("操作类型", max_length=20, choices=ACTION_CHOICES)
    change_amount = models.FloatField("变动数量(+/-)")
    quantity_after = models.FloatField("变动后余量(快照)")
    note = models.CharField("备注/原因", max_length=200, blank=True)
    created_at = models.DateTimeField("操作时间", auto_now_add=True)

    class Meta:
        verbose_name = "库存变动日志"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

class CostConfigLog(models.Model):
    """
    配置变更记录
    """
    config = models.ForeignKey(CostConfig, on_delete=models.CASCADE, verbose_name="关联配置项")
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        verbose_name="操作人"
    )
    old_price = models.DecimalField("原价格", max_digits=10, decimal_places=2)
    new_price = models.DecimalField("新价格", max_digits=10, decimal_places=2)
    changed_at = models.DateTimeField("变更时间", auto_now_add=True)

    class Meta:
        verbose_name = "价格变更记录"
        ordering = ['-changed_at']
        verbose_name_plural = verbose_name