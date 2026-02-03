# Django基础ORM管理
from django.db import models
# 表单基础模型
from .core import BaseProductionStep
# 批号生成器
from ..utils.batch_generator import generate_batch_number
# 引入常量
from .. import constants
# 引入库存模型
from .inventory import Inventory
from .audit import InventoryLog


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

    # =========================================================
    # 5. 库存映射配置
    # =========================================================
    INVENTORY_MAPPING = {
        'raw_dcb': constants.KEY_RAW_DCB,
        'raw_nacn': constants.KEY_RAW_NACN,
        'raw_tbab': constants.KEY_RAW_TBAB,
        'raw_alkali': constants.KEY_RAW_ALKALI,
        'crude_weight': constants.KEY_INTER_CVN_CRUDE,
        'recovered_dcb_amount': constants.KEY_RECYCLED_DCB,
    }

    class Meta(BaseProductionStep.Meta):
        verbose_name = "1-CVN合成"
        verbose_name_plural = verbose_name

    # --- 核心属性：剩余可用量 ---
    @property
    def remaining_weight(self):
        """批次里还剩多少粗蒸CVN"""
        return max(0, self.crude_weight - self.consumed_weight)

    # --- 核心逻辑：自动生成批号 + 库存扣减 ---
    def save(self, *args, **kwargs):
        # 0. 自动生成批号
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVNSynthesis, "CVN-CU")

        # 1. 获取旧对象以计算差值
        old_instance = None
        if self.pk:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
            except self.__class__.DoesNotExist:
                pass

        # 2. 遍历映射，处理库存
        for field_name, inventory_key in self.INVENTORY_MAPPING.items():
            current_val = getattr(self, field_name, 0) or 0
            old_val = getattr(old_instance, field_name, 0) or 0 if old_instance else 0
            
            # 计算差异：本次操作导致的数值变化量
            diff = current_val - old_val

            if diff != 0:
                try:
                    inv = Inventory.objects.get(key=inventory_key)
                    
                    # 判断是投入(消耗)还是产出(增加)
                    # 逻辑：字段名以 'raw_' 开头视为投入，否则视为产出(如 crude_weight)
                    is_input = field_name.startswith('raw_')
                    
                    if is_input:
                        # 投入：消耗库存，所以减去 diff
                        # 例如：原来消耗100，现在消耗120 (diff=+20)，库存应 -20
                        change_amount = -diff
                    else:
                        # 产出：增加库存，所以加上 diff
                        # 例如：原来产出100，现在产出120 (diff=+20)，库存应 +20
                        change_amount = diff

                    inv.quantity += change_amount
                    inv.save()

                    # 记录日志
                    InventoryLog.objects.create(
                        inventory=inv,
                        action_type='production',
                        change_amount=change_amount,
                        quantity_after=inv.quantity,
                        note=f"生产批次 {self.batch_no} 自动变动 ({field_name})"
                    )
                except Inventory.DoesNotExist:
                    pass # 忽略未初始化的库存

        # 3. 执行原有保存
        super().save(*args, **kwargs)
