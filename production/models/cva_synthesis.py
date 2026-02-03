from django.db import models, transaction
from django.db.models import JSONField, F
from django.core.exceptions import ValidationError

from .core import BaseProductionStep
# 引入CVN 精馏模型
from .cvn_distillation import CVNDistillation
from ..utils.batch_generator import generate_batch_number
# 引入常量
from .. import constants
# 引入库存模型
from .inventory import Inventory
from .audit import InventoryLog


# =========================================================
# 工艺第三步： CVA合成
# =========================================================
class CVASynthesis(BaseProductionStep):
    """
    Step 3: CVA 合成及脱水
    逻辑：投入CVN精品(Step 2) + 酸碱 -> 反应 -> 脱水 -> CVA粗品
    """

    # =========================================================
    # 1. 投入 (Input)
    # =========================================================
    # 来源：Step 2 (CVN 精馏)
    input_sources = JSONField(
        "投入CVN精品来源",
        default=list,
        help_text="""
        结构：[{
            "batch_no": "CVN-JING-2026...", 
            "use_weight": 200, 
            "content_cvn": 99.5, 
            "note": "..."
        }]
        """
    )

    input_total_weight = models.FloatField("投入CVN精品总重(kg)", default=0)

    # 辅料
    raw_hcl = models.FloatField("投入-盐酸(kg)", default=0)
    raw_alkali = models.FloatField("投入-液碱(kg)", default=0)

    # =========================================================
    # 2. 产出 (Output) - CVA 粗品 (脱水后)
    # =========================================================
    crude_weight = models.FloatField("产出-CVA粗品重量(kg)", default=0, help_text="脱水后的实际称重")

    # 库存核心：Step 4 (CVC合成) 将从这里领料
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False)

    # =========================================================
    # 3. 质检 (QC)
    # =========================================================
    content_cva = models.FloatField("中控-CVA含量%", null=True, blank=True)
    content_cvn = models.FloatField("中控-CVN残留%", null=True, blank=True, help_text="标准应 < 0.5%")
    content_water = models.FloatField("中控-水分%", null=True, blank=True, help_text="脱水效果指标")

    # =========================================================
    # 4. 库存映射配置
    # =========================================================
    INVENTORY_MAPPING = {
        'raw_hcl': constants.KEY_RAW_HCL,
        'raw_alkali': constants.KEY_RAW_ALKALI,
        'crude_weight': constants.KEY_INTER_CVA_CRUDE,
    }

    class Meta(BaseProductionStep.Meta):
        verbose_name = "3-CVA合成"
        verbose_name_plural = verbose_name

    # --- 核心属性：剩余可用量 (供 Step 4 使用) ---
    @property
    def remaining_weight(self):
        return max(0, self.crude_weight - self.consumed_weight)

    @property
    def status_label(self):
        """
        批次生命周期状态
        逻辑：根据 crude_weight (产出) 和 consumed_weight (已领) 动态判断
        """
        # 容错：防止产出为0时的除法错误（虽然 clean 已校验）
        if self.crude_weight <= 0:
            return "异常批次"

        if self.consumed_weight <= 0:
            return "🟢 全新待领"
        elif self.remaining_weight <= 0:  # 这里的 remaining_weight 已经在上面定义过了
            return "⚫ 耗尽归档"
        else:
            return "🟡 部分领用"

    # 让 Admin 后台可以按这个字段排序（按剩余量排序）
    status_label.fget.short_description = "当前状态"
    status_label.fget.admin_order_field = 'consumed_weight'

    # --- 校验逻辑 ---
    def clean(self):
        super().clean()

        calculated_total = 0

        # 获取旧对象用于库存回滚计算
        old_instance = None
        if self.pk:
            try:
                old_instance = CVASynthesis.objects.get(pk=self.pk)
            except CVASynthesis.DoesNotExist:
                pass

        for item in self.input_sources:
            batch_no = item.get('batch_no')
            try:
                use_weight = float(item.get('use_weight', 0))
            except (ValueError, TypeError):
                raise ValidationError(f"批号 {batch_no} 重量格式错误")

            if use_weight <= 0:
                raise ValidationError("投入重量必须大于0")

            calculated_total += use_weight

            # 1. 查找源头 (Step 2)
            try:
                source_batch = CVNDistillation.objects.get(batch_no=batch_no)
            except CVNDistillation.DoesNotExist:
                raise ValidationError(f"CVN精品批号 {batch_no} 不存在")

            # 2. 计算库存可用量
            recoverable = 0
            if old_instance:
                for old_item in old_instance.input_sources:
                    if old_item.get('batch_no') == batch_no:
                        recoverable = float(old_item.get('use_weight', 0))
                        break

            # 注意：这里调用的是 source_batch (Step 2) 的 remaining_weight
            # 如果没在 CVNDistillation 加这个属性，这里会报错
            if hasattr(source_batch, 'remaining_weight'):
                max_allowable = source_batch.remaining_weight + recoverable
                if use_weight > max_allowable:
                    raise ValidationError(f"批号 {batch_no} 库存不足。可用: {max_allowable}kg")
            else:
                # 临时容错，防止代码直接崩（建议开发时去掉此 else）
                pass

        if abs(self.input_total_weight - calculated_total) > 0.1:
            raise ValidationError("投入CVN总重与明细不符")

    # --- 保存逻辑 (扣减 Step 2 库存 + 扣减普通原料 + 产出CVA粗品) ---
    @transaction.atomic
    def save(self, *args, **kwargs):
        # 0. 自动生成批号
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVASynthesis, "CVA")

        # 1. 获取旧对象以计算差值
        old_instance = None
        if self.pk:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
            except self.__class__.DoesNotExist:
                pass

        # =========================================================
        # Part A: 处理 JSON 投入 (input_sources) -> 消耗 CVN精品
        # =========================================================
        
        # A.1 计算新旧总投入量
        current_input_total = 0
        for item in self.input_sources:
            current_input_total += float(item.get('use_weight', 0))
        
        old_input_total = 0
        if old_instance:
            for item in old_instance.input_sources:
                old_input_total += float(item.get('use_weight', 0))
        
        # A.2 计算差异 (消耗量变化)
        input_diff = current_input_total - old_input_total
        
        # A.3 更新 Inventory 表 (CVN精品)
        if input_diff != 0:
            try:
                inv_pure = Inventory.objects.get(key=constants.KEY_INTER_CVN_PURE)
                # 投入是消耗，所以库存减去 diff
                inv_pure.quantity -= input_diff
                inv_pure.save()
                
                InventoryLog.objects.create(
                    inventory=inv_pure,
                    action_type='production',
                    change_amount=-input_diff,
                    quantity_after=inv_pure.quantity,
                    note=f"生产批次 {self.batch_no} 自动消耗 (input_sources)"
                )
            except Inventory.DoesNotExist:
                pass

        # A.4 更新源头批次 (CVNDistillation) 的 consumed_weight
        # 先“归还”旧的库存
        if old_instance:
            for item in old_instance.input_sources:
                batch_no = item.get('batch_no')
                weight = float(item.get('use_weight', 0))
                CVNDistillation.objects.filter(batch_no=batch_no).update(
                    consumed_weight=models.F('consumed_weight') - weight
                )

        # 再扣减新的库存
        for item in self.input_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVNDistillation.objects.filter(batch_no=batch_no).update(
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

        # 3. 执行原有保存
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        """
        删除逻辑：
        1. 归还源头批次 (CVNDistillation) 的 consumed_weight。
        2. 归还 Inventory 表中的 CVN精品库存。
        3. 回滚 Inventory 表中的普通原料消耗和CVA粗品产出。
        """
        # 1. 归还源头批次
        for item in self.input_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVNDistillation.objects.filter(batch_no=batch_no).update(
                consumed_weight=models.F('consumed_weight') - weight
            )
        
        # 2. 归还 Inventory 表中的 CVN精品库存 (相当于把消耗的加回去)
        current_input_total = 0
        for item in self.input_sources:
            current_input_total += float(item.get('use_weight', 0))
            
        if current_input_total > 0:
            try:
                inv_pure = Inventory.objects.get(key=constants.KEY_INTER_CVN_PURE)
                inv_pure.quantity += current_input_total
                inv_pure.save()
                
                InventoryLog.objects.create(
                    inventory=inv_pure,
                    action_type='correction',
                    change_amount=current_input_total,
                    quantity_after=inv_pure.quantity,
                    note=f"删除批次 {self.batch_no} 回滚消耗 (CVN精品)"
                )
            except Inventory.DoesNotExist:
                pass

        # 3. 回滚 Inventory 表中的普通原料消耗和CVA粗品产出
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
