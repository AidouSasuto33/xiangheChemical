from django.db import models
from django.conf import settings
from .inventory import Inventory
from .core import CostConfig


# =========================================================
# A. 库存变动日志 (审计核心)
# =========================================================
class InventoryLog(models.Model):
    """
    库存变动流水账
    记录：购入、卖出、生产消耗、盘点修正
    """
    ACTION_CHOICES = [
        ('purchase', '购入/入库'),  # 对应“购入”按钮 (数量 +)
        ('sale', '销售/出库'),  # 对应“卖出”按钮 (数量 -)
        ('correction', '盘点/修正'),  # 对应“盘库修正”按钮 (数量 +/-)
        ('production', '生产消耗/产出'),  # 系统自动记录 (Step1-5 Save触发)
    ]

    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, verbose_name="关联物料")

    # 谁干的？(自动记录生产时，operator可能为空，或者设为系统机器人)
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="操作人"
    )

    action_type = models.CharField("操作类型", max_length=20, choices=ACTION_CHOICES)

    # 核心数据
    change_amount = models.FloatField("变动数量(+/-)")
    quantity_after = models.FloatField("变动后余量(快照)")

    # 备注 (比如：盘点发现桶漏了，修正-50kg)
    note = models.CharField("备注/原因", max_length=200, blank=True)

    created_at = models.DateTimeField("操作时间", auto_now_add=True)

    class Meta:
        verbose_name = "库存变动日志"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']


# =========================================================
# B. 配置变更日志 (趋势分析)
# =========================================================
class CostConfigLog(models.Model):
    """
    配置变更记录
    记录：谁把二氯丁烷价格从 8000 改成了 8500
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

    reason = models.CharField("修改原因", max_length=200, blank=True, help_text="如：供应商调价")

    created_at = models.DateTimeField("修改时间", auto_now_add=True)

    class Meta:
        verbose_name = "价格/配置变更记录"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']