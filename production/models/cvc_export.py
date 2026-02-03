from django.db import models, transaction
from django.db.models import JSONField, F
from django.core.exceptions import ValidationError

from .core import BaseProductionStep
# 引入 Step 4 (CVC 内销) 作为原料来源
from .cvc_synthesis import CVCSynthesis
from ..utils.batch_generator import generate_batch_number
# 引入常量
from .. import constants
# 引入库存模型
from .inventory import Inventory
from .audit import InventoryLog


# =========================================================
# 工艺第五步： CVC外销精制
# =========================================================
class CVCExport(BaseProductionStep):
    """
    Step 5: CVC 外销精制 (Wai Xiao)
    逻辑：投入CVC合格品(Step 4) -> 二次精馏 -> CVC精品
    """

    # =========================================================
    # 1. 投入 (Input)
    # =========================================================
    # 来源：Step 4 (CVC 内销合格品)
    input_cvc_sources = JSONField(
        "投入CVC合格品来源",
        default=list,
        help_text="""
        结构：[{
            "batch_no": "CVC-NX-2026...", 
            "use_weight": 1000, 
            "content_cvc": 99.1, 
            "note": "..."
        }]
        """
    )

    input_total_weight = models.FloatField("投入总重量(kg)", default=0)

    # =========================================================
    # 2. 产出 (Output) - 精品
    # =========================================================
    # 这是一个物理称重值，肯定会比投入总重量少（因为有损耗）
    premium_weight = models.FloatField("产出-CVC精品重量(kg)", default=0, help_text="二次蒸馏后的实际装桶重量")

    # =========================================================
    # 3. 精品检测 (Premium QC)
    # =========================================================
    product_content_cvc = models.FloatField("精品-CVC含量%", null=True, blank=True)
    product_content_cva = models.FloatField("精品-CVA含量%", null=True, blank=True)

    # =========================================================
    # 4. 库存 (Inventory)
    # =========================================================
    # 如果系统还要管销售发货，这个字段依然需要
    consumed_weight = models.FloatField("已领用/发货重量(kg)", default=0, editable=False)

    # =========================================================
    # 5. 库存映射配置
    # =========================================================
    INVENTORY_MAPPING = {
        'premium_weight': constants.KEY_PROD_CVC_WX,
    }

    class Meta(BaseProductionStep.Meta):
        verbose_name = "5-CVC外销精制"
        verbose_name_plural = verbose_name

    # --- 核心属性 ---
    @property
    def remaining_weight(self):
        return max(0, self.premium_weight - self.consumed_weight)

    def clean(self):
        super().clean()

        calculated_total = 0
        old_instance = None
        if self.pk:
            try:
                old_instance = CVCExport.objects.get(pk=self.pk)
            except CVCExport.DoesNotExist:
                pass

        # 校验 CVC 合格品来源
        for item in self.input_cvc_sources:
            batch_no = item.get('batch_no')
            try:
                use_weight = float(item.get('use_weight', 0))
            except (ValueError, TypeError):
                raise ValidationError(f"批号 {batch_no} 重量格式错误")

            if use_weight <= 0:
                raise ValidationError("投入重量必须大于0")

            calculated_total += use_weight

            # 1. 查找源头 (Step 4)
            try:
                source_batch = CVCSynthesis.objects.get(batch_no=batch_no)
            except CVCSynthesis.DoesNotExist:
                raise ValidationError(f"CVC内销批号 {batch_no} 不存在")

            # 2. 计算库存可用量
            recoverable = 0
            if old_instance:
                for old_item in old_instance.input_cvc_sources:
                    if old_item.get('batch_no') == batch_no:
                        recoverable = float(old_item.get('use_weight', 0))
                        break

            # 确保 Step 4 有 remaining_weight 属性
            if hasattr(source_batch, 'remaining_weight'):
                max_allowable = source_batch.remaining_weight + recoverable
                if use_weight > max_allowable:
                    raise ValidationError(f"批号 {batch_no} 库存不足。可用: {max_allowable}kg")

        if abs(self.input_total_weight - calculated_total) > 0.1:
            raise ValidationError("投入总重与明细不符")

        # 逻辑校验：产出不能大于投入（物理定律）
        if self.premium_weight > self.input_total_weight:
            # 除非有极其特殊的情况，否则精馏不可能变重
            # 用于确保文员填错警告
            raise ValidationError("产出精品重量不能大于投入重量")

    @transaction.atomic
    def save(self, *args, **kwargs):
        # 批号生成：CVC-WX (外销/Wai Xiao)
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVCExport, "CVC-WX")

        # 1. 获取旧对象以计算差值
        old_instance = None
        if self.pk:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
            except self.__class__.DoesNotExist:
                pass

        # =========================================================
        # Part A: 处理 JSON 投入 (input_cvc_sources) -> 消耗 CVC内销合格品
        # =========================================================
        
        # A.1 计算新旧总投入量
        current_input_total = 0
        for item in self.input_cvc_sources:
            current_input_total += float(item.get('use_weight', 0))
        
        old_input_total = 0
        if old_instance:
            for item in old_instance.input_cvc_sources:
                old_input_total += float(item.get('use_weight', 0))
        
        # A.2 计算差异 (消耗量变化)
        input_diff = current_input_total - old_input_total
        
        # A.3 更新 Inventory 表 (CVC内销合格品)
        if input_diff != 0:
            try:
                inv_nx = Inventory.objects.get(key=constants.KEY_PROD_CVC_NX)
                # 投入是消耗，所以库存减去 diff
                inv_nx.quantity -= input_diff
                inv_nx.save()
                
                InventoryLog.objects.create(
                    inventory=inv_nx,
                    action_type='production',
                    change_amount=-input_diff,
                    quantity_after=inv_nx.quantity,
                    note=f"生产批次 {self.batch_no} 自动消耗 (input_cvc_sources)"
                )
            except Inventory.DoesNotExist:
                pass

        # A.4 更新源头批次 (CVCSynthesis) 的 consumed_weight
        # 先“归还”旧的库存
        if old_instance:
            for item in old_instance.input_cvc_sources:
                batch_no = item.get('batch_no')
                weight = float(item.get('use_weight', 0))
                CVCSynthesis.objects.filter(batch_no=batch_no).update(
                    consumed_weight=models.F('consumed_weight') - weight
                )

        # 再扣减新的库存
        for item in self.input_cvc_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVCSynthesis.objects.filter(batch_no=batch_no).update(
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
        1. 归还源头批次 (CVCSynthesis) 的 consumed_weight。
        2. 归还 Inventory 表中的 CVC内销合格品库存。
        3. 回滚 Inventory 表中的 CVC外销精品产出。
        """
        # 1. 归还源头批次
        for item in self.input_cvc_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVCSynthesis.objects.filter(batch_no=batch_no).update(
                consumed_weight=models.F('consumed_weight') - weight
            )
        
        # 2. 归还 Inventory 表中的 CVC内销合格品库存 (相当于把消耗的加回去)
        current_input_total = 0
        for item in self.input_cvc_sources:
            current_input_total += float(item.get('use_weight', 0))
            
        if current_input_total > 0:
            try:
                inv_nx = Inventory.objects.get(key=constants.KEY_PROD_CVC_NX)
                inv_nx.quantity += current_input_total
                inv_nx.save()
                
                InventoryLog.objects.create(
                    inventory=inv_nx,
                    action_type='correction',
                    change_amount=current_input_total,
                    quantity_after=inv_nx.quantity,
                    note=f"删除批次 {self.batch_no} 回滚消耗 (CVC内销)"
                )
            except Inventory.DoesNotExist:
                pass

        # 3. 回滚 Inventory 表中的 CVC外销精品产出
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
