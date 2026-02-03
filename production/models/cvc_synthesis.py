from django.db import models, transaction
from django.db.models import JSONField, F
from django.core.exceptions import ValidationError

from .core import BaseProductionStep
# 引入 Step 3 (CVA合成) 作为原料来源
from .cva_synthesis import CVASynthesis
from ..utils.batch_generator import generate_batch_number
# 引入常量
from .. import constants
# 引入库存模型
from .inventory import Inventory
from .audit import InventoryLog


# =========================================================
# 工艺第四步： CVC合成
# =========================================================
class CVCSynthesis(BaseProductionStep):
    """
    Step 4: CVC 合成 (内销/普通级)
    逻辑：投入CVA粗品(Step 3) + 二氯亚砜 -> 氯化反应(多点中控) -> 精馏 -> CVC成品
    """

    # =========================================================
    # 1. 投入 (Input)
    # =========================================================
    # 来源：Step 3 (CVA 合成)
    input_cva_sources = JSONField(
        "投入CVA粗品来源",
        default=list,
        help_text="""
        结构：[{
            "batch_no": "CVA-2026...", 
            "use_weight": 500, 
            "content_cva": 98.5, 
            "note": "..."
        }]
        """
    )

    input_total_cva_weight = models.FloatField("投入CVA总重(kg)", default=0)

    # 关键辅料
    raw_socl2 = models.FloatField("投入-二氯亚砜(kg)", default=0)

    # =========================================================
    # 2. 过程监控 (IPC - In-Process Control)
    # =========================================================
    # 支持多条中控记录
    ipc_logs = JSONField(
        "合成中控记录",
        default=list,
        help_text="""
        结构示例：
        [
            {"time": "10:00", "duration_hours": 2.5, "ipc_cvc": 85.5, "ipc_cva": 14.0, "note": "未反应完"},
            {"time": "12:00", "duration_hours": 4.5, "ipc_cvc": 99.1, "ipc_cva": 0.2, "note": "合格停火"}
        ]
        """
    )

    # =========================================================
    # 3. 产出 (Output) - 精馏后
    # =========================================================
    # 前馏份，精馏过程中先出来的头份，通常是不纯的，需要记录重量。可能回收或废弃？
    distillation_head_weight = models.FloatField("产出-前馏份/头酒(kg)", default=0,
                                                 help_text="精馏初期的不合格部分，通常回用或报废")

    # 合格品 (真正的产量)
    product_weight = models.FloatField("产出-CVC合格品重量(kg)", default=0)

    # 最终质检 (Final QC)
    product_content = models.FloatField("成品-CVC含量%", null=True, blank=True, help_text="精馏后的最终纯度")

    # =========================================================
    # 4. 库存逻辑
    # =========================================================
    # 这里的库存将被：1. 销售发货 2. Step 5 (外销精制) 领用
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False)

    # =========================================================
    # 5. 库存映射配置
    # =========================================================
    INVENTORY_MAPPING = {
        'raw_socl2': constants.KEY_RAW_SOCL2,
        'distillation_head_weight': constants.KEY_WASTE_HEAD,
        'product_weight': constants.KEY_PROD_CVC_NX,
    }

    class Meta(BaseProductionStep.Meta):
        verbose_name = "4-CVC合成(内销)"
        verbose_name_plural = verbose_name

    # --- 核心属性：剩余可用量 (供 Step 5 或 销售 使用) ---
    @property
    def remaining_weight(self):
        return max(0, self.product_weight - self.consumed_weight)

    def clean(self):
        super().clean()

        calculated_total = 0
        old_instance = None
        if self.pk:
            try:
                old_instance = CVCSynthesis.objects.get(pk=self.pk)
            except CVCSynthesis.DoesNotExist:
                pass

        # 校验 CVA 来源
        for item in self.input_cva_sources:
            batch_no = item.get('batch_no')
            try:
                use_weight = float(item.get('use_weight', 0))
            except (ValueError, TypeError):
                raise ValidationError(f"批号 {batch_no} 重量格式错误")

            if use_weight <= 0:
                raise ValidationError("投入重量必须大于0")

            calculated_total += use_weight

            # 1. 查找源头 (Step 3)
            try:
                source_batch = CVASynthesis.objects.get(batch_no=batch_no)
            except CVASynthesis.DoesNotExist:
                raise ValidationError(f"CVA粗品批号 {batch_no} 不存在")

            # 2. 计算库存可用量
            recoverable = 0
            if old_instance:
                for old_item in old_instance.input_cva_sources:
                    if old_item.get('batch_no') == batch_no:
                        recoverable = float(old_item.get('use_weight', 0))
                        break

            # 确保 Step 3 有 remaining_weight 属性
            if hasattr(source_batch, 'remaining_weight'):
                max_allowable = source_batch.remaining_weight + recoverable
                if use_weight > max_allowable:
                    raise ValidationError(f"批号 {batch_no} 库存不足。可用: {max_allowable}kg")

        if abs(self.input_total_cva_weight - calculated_total) > 0.1:
            raise ValidationError("投入CVA总重与明细不符")

    @transaction.atomic
    def save(self, *args, **kwargs):
        # 批号生成：CVC-NX (内销)
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVCSynthesis, "CVC-NX")

        # 1. 获取旧对象以计算差值
        old_instance = None
        if self.pk:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
            except self.__class__.DoesNotExist:
                pass

        # =========================================================
        # Part A: 处理 JSON 投入 (input_cva_sources) -> 消耗 CVA粗品
        # =========================================================
        
        # A.1 计算新旧总投入量
        current_input_total = 0
        for item in self.input_cva_sources:
            current_input_total += float(item.get('use_weight', 0))
        
        old_input_total = 0
        if old_instance:
            for item in old_instance.input_cva_sources:
                old_input_total += float(item.get('use_weight', 0))
        
        # A.2 计算差异 (消耗量变化)
        input_diff = current_input_total - old_input_total
        
        # A.3 更新 Inventory 表 (CVA粗品)
        if input_diff != 0:
            try:
                inv_crude = Inventory.objects.get(key=constants.KEY_INTER_CVA_CRUDE)
                # 投入是消耗，所以库存减去 diff
                inv_crude.quantity -= input_diff
                inv_crude.save()
                
                InventoryLog.objects.create(
                    inventory=inv_crude,
                    action_type='production',
                    change_amount=-input_diff,
                    quantity_after=inv_crude.quantity,
                    note=f"生产批次 {self.batch_no} 自动消耗 (input_cva_sources)"
                )
            except Inventory.DoesNotExist:
                pass

        # A.4 更新源头批次 (CVASynthesis) 的 consumed_weight
        # 先“归还”旧的库存
        if old_instance:
            for item in old_instance.input_cva_sources:
                batch_no = item.get('batch_no')
                weight = float(item.get('use_weight', 0))
                CVASynthesis.objects.filter(batch_no=batch_no).update(
                    consumed_weight=models.F('consumed_weight') - weight
                )

        # 再扣减新的库存
        for item in self.input_cva_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVASynthesis.objects.filter(batch_no=batch_no).update(
                consumed_weight=models.F('consumed_weight') + weight
            )

        # =========================================================
        # Part B: 处理普通映射 (INVENTORY_MAPPING)
        # =========================================================
        for field_name, inventory_key in self.INVENTORY_MAPPING.items():
            current_val = getattr(self, field_name, 0) or 0
            old_val = getattr(old_instance, field_name, 0) or 0 if old_instance else 0
            
            diff = current_val - old_val

            if diff != 0:
                try:
                    inv = Inventory.objects.get(key=inventory_key)
                    
                    # 判断是投入(消耗)还是产出(增加)
                    is_input = field_name.startswith('raw_')
                    
                    if is_input:
                        # 投入：消耗库存，所以减去 diff
                        change_amount = -diff
                    else:
                        # 产出：增加库存，所以加上 diff
                        change_amount = diff

                    inv.quantity += change_amount
                    inv.save()

                    InventoryLog.objects.create(
                        inventory=inv,
                        action_type='production',
                        change_amount=change_amount,
                        quantity_after=inv.quantity,
                        note=f"生产批次 {self.batch_no} 自动变动 ({field_name})"
                    )
                except Inventory.DoesNotExist:
                    pass

        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        """
        删除逻辑：
        1. 归还源头批次 (CVASynthesis) 的 consumed_weight。
        2. 归还 Inventory 表中的 CVA粗品库存。
        3. 回滚 Inventory 表中的普通原料消耗和CVC成品产出。
        """
        # 1. 归还源头批次
        for item in self.input_cva_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVASynthesis.objects.filter(batch_no=batch_no).update(
                consumed_weight=models.F('consumed_weight') - weight
            )
        
        # 2. 归还 Inventory 表中的 CVA粗品库存 (相当于把消耗的加回去)
        current_input_total = 0
        for item in self.input_cva_sources:
            current_input_total += float(item.get('use_weight', 0))
            
        if current_input_total > 0:
            try:
                inv_crude = Inventory.objects.get(key=constants.KEY_INTER_CVA_CRUDE)
                inv_crude.quantity += current_input_total
                inv_crude.save()
                
                InventoryLog.objects.create(
                    inventory=inv_crude,
                    action_type='correction',
                    change_amount=current_input_total,
                    quantity_after=inv_crude.quantity,
                    note=f"删除批次 {self.batch_no} 回滚消耗 (CVA粗品)"
                )
            except Inventory.DoesNotExist:
                pass

        # 3. 回滚 Inventory 表中的普通原料消耗和CVC成品产出
        for field_name, inventory_key in self.INVENTORY_MAPPING.items():
            val = getattr(self, field_name, 0) or 0
            if val != 0:
                try:
                    inv = Inventory.objects.get(key=inventory_key)
                    is_input = field_name.startswith('raw_')
                    
                    if is_input:
                        # 原来是消耗(减)，现在要加回去
                        change_amount = val
                    else:
                        # 原来是产出(加)，现在要减回去
                        change_amount = -val
                        
                    inv.quantity += change_amount
                    inv.save()
                    
                    InventoryLog.objects.create(
                        inventory=inv,
                        action_type='correction',
                        change_amount=change_amount,
                        quantity_after=inv.quantity,
                        note=f"删除批次 {self.batch_no} 回滚 ({field_name})"
                    )
                except Inventory.DoesNotExist:
                    pass

        super().delete(*args, **kwargs)
