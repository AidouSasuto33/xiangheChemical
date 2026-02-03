# Django基础ORM管理
from django.db import models
# 引入基础模型
from .core import BaseProductionStep
# 引入 CVN 合成模型
from .cvn_synthesis import CVNSynthesis

# 引入 Postgres 特有的 ArrayField (虽然 JSONField 更通用，但这里用 JSON 兼容性更好)
from django.db.models import JSONField
# 批号生成器
from ..utils.batch_generator import generate_batch_number
# Django事务管理
from django.db import transaction
# Django异常处理
from django.core.exceptions import ValidationError
# 引入常量
from .. import constants
# 引入库存模型
from .inventory import Inventory
from .audit import InventoryLog


# =========================================================
# 工艺第二步： CVN精馏
# =========================================================
class CVNDistillation(BaseProductionStep):
    """
    Step 2: CVN 精馏
    核心逻辑：多批次领料 -> 混合精馏 -> 产出精品 + 釜残
    """

    # =========================================================
    # 1. 投入 (Input) - 核心库存交互
    # =========================================================
    # 数据结构示例：
    # [
    #   {"batch_no": "CVN-CU-20260201-01", "use_weight": 500, "content_cvn": 80.5, "content_dcb": 10.2, "content_adn": 2.1, "note": "主料"},
    #   {"batch_no": "CVN-CU-20260201-02", "use_weight": 120, "content_cvn": 82.1, "content_dcb": 11.2, "content_adn": 1.1, "note": "尾料凑数"}
    # ]
    input_sources = JSONField(
        "投入来源明细",
        default=list,
        help_text="""
        标准结构：
        [
            {
                "batch_no": "CVN-CU-20260201-01", 
                "use_weight": 500,        # 投入了多少 (kg)
                "content_cvn": 80.5,      # 该批次的 CVN 含量快照 (%)
                "content_dcb": 10.2,      # 该批次的 DCB 含量快照 (%)
                "content_adn": 2.1,       # 该批次的 己二腈 含量快照 (%)
                "note": "主料"
            },
            ...
        ]
        """
    )

    input_total_weight = models.FloatField("投入总重量(kg)", default=0, help_text="应等于来源明细重量之和")

    # =========================================================
    # 2. 精馏前组份 (Pre-Distillation Composition)
    # =========================================================
    # 虽然可以通过 input_sources 算加权平均，但工厂可能有实测值，故保留字段
    pre_cvn_content = models.FloatField("精前-CVN含量%", null=True, blank=True)
    pre_dcb_content = models.FloatField("精前-DCB含量%", null=True, blank=True)
    pre_adn_content = models.FloatField("精前-己二腈含量%", null=True, blank=True)

    # =========================================================
    # 3. 产出 (Output)
    # =========================================================
    output_weight = models.FloatField("产出-CVN精品重量(kg)", default=0)

    output_cvn_content = models.FloatField("精品-CVN含量%", null=True, blank=True)
    output_dcb_content = models.FloatField("精品-DCB含量%", null=True, blank=True)
    output_adn_content = models.FloatField("精品-己二腈含量%", null=True, blank=True)

    # 库存核心字段：记录已被CVA合成工段领用了多少
    consumed_weight = models.FloatField("已领用重量(kg)", default=0, editable=False, help_text="系统自动更新，不可手改")

    # --- 核心属性：剩余可用量 ---
    @property
    def remaining_weight(self):
        """批次里还剩多少精馏CVM"""
        return max(0, self.output_weight - self.consumed_weight)

    # =========================================================
    # 4. 固废 (Waste)
    # =========================================================
    residue_weight = models.FloatField("釜残重量(kg)", default=0, help_text="危废处理成本依据")

    # =========================================================
    # 5. 库存映射配置
    # =========================================================
    INVENTORY_MAPPING = {
        'output_weight': constants.KEY_INTER_CVN_PURE,
    }


    class Meta(BaseProductionStep.Meta):
        verbose_name = "2-CVN精馏"
        verbose_name_plural = verbose_name

    def clean(self):
        """
        数据校验防线：
        1. 验证 batch_no 是否存在。
        2. 验证重量是否超标 (Validation)。
        3. 验证 input_total_weight 是否一致。
        """
        super().clean()

        calculated_total = 0

        # 预先获取当前数据库里的旧记录（用于处理修改场景下的库存回滚逻辑）
        old_instance = None
        if self.pk:
            try:
                old_instance = CVNDistillation.objects.get(pk=self.pk)
            except CVNDistillation.DoesNotExist:
                pass

        # 遍历输入的来源列表
        for item in self.input_sources:
            batch_no = item.get('batch_no')
            try:
                use_weight = float(item.get('use_weight', 0))
            except (ValueError, TypeError):
                raise ValidationError(f"批号 {batch_no} 的重量格式错误")

            if use_weight <= 0:
                raise ValidationError(f"投入重量必须大于0")

            calculated_total += use_weight

            # 查找源头批次
            try:
                source_batch = CVNSynthesis.objects.get(batch_no=batch_no)
            except CVNSynthesis.DoesNotExist:
                raise ValidationError(f"源批号 {batch_no} 不存在，请检查拼写")

            # --- 库存超标校验 (核心难点) ---
            # 可用量 = 当前仓库剩余 + (如果是修改，加上我上次占用的量)
            recoverable_stock = 0
            if old_instance:
                # 在旧记录里找找看，上次我用了这个批次多少？
                for old_item in old_instance.input_sources:
                    if old_item.get('batch_no') == batch_no:
                        recoverable_stock = float(old_item.get('use_weight', 0))
                        break

            max_allowable = source_batch.remaining_weight + recoverable_stock

            if use_weight > max_allowable:
                raise ValidationError(
                    f"批号 {batch_no} 库存不足。剩余: {source_batch.remaining_weight}kg，"
                    f"当前编辑回退后可用: {max_allowable}kg，试图使用: {use_weight}kg"
                )

        # 校验总和
        # 允许 0.1kg 的浮动误差
        if abs(self.input_total_weight - calculated_total) > 0.1:
            raise ValidationError(
                f"投入总重量 ({self.input_total_weight}) 与明细加和 ({calculated_total}) 不一致，请检查。")

    @transaction.atomic
    def save(self, *args, **kwargs):
        """
        保存逻辑：
        1. 生成批号。
        2. 处理库存扣减 (先回滚旧的，再扣减新的)。
        3. 处理 Inventory 表的库存变动。
        """
        # 1. 自动生成批号
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVNDistillation, "CVN-JING")

        # 2. 获取旧对象以计算差值
        old_instance = None
        if self.pk:
            try:
                old_instance = self.__class__.objects.get(pk=self.pk)
            except self.__class__.DoesNotExist:
                pass

        # 3. 处理 input_sources 的库存逻辑 (CVN粗品消耗)
        # 3.1 计算新旧总投入量
        current_input_total = 0
        for item in self.input_sources:
            current_input_total += float(item.get('use_weight', 0))

        old_input_total = 0
        if old_instance:
            for item in old_instance.input_sources:
                old_input_total += float(item.get('use_weight', 0))

        # 3.2 计算差异 (消耗量变化)
        input_diff = current_input_total - old_input_total

        # 3.3 更新 Inventory 表 (CVN粗品)
        if input_diff != 0:
            try:
                inv_crude = Inventory.objects.get(key=constants.KEY_INTER_CVN_CRUDE)
                # 投入是消耗，所以库存减去 diff
                inv_crude.quantity -= input_diff
                inv_crude.save()

                InventoryLog.objects.create(
                    inventory=inv_crude,
                    action_type='production',
                    change_amount=-input_diff,
                    quantity_after=inv_crude.quantity,
                    note=f"生产批次 {self.batch_no} 自动消耗 (input_sources)"
                )
            except Inventory.DoesNotExist:
                pass

        # 3.4 更新源头批次 (CVNSynthesis) 的 consumed_weight
        # A. 如果是修改现有的记录：先“归还”旧的库存
        if old_instance:
            for item in old_instance.input_sources:
                batch_no = item.get('batch_no')
                weight = float(item.get('use_weight', 0))
                CVNSynthesis.objects.filter(batch_no=batch_no).update(
                    consumed_weight=models.F('consumed_weight') - weight
                )

        # B. 扣减新的库存
        for item in self.input_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVNSynthesis.objects.filter(batch_no=batch_no).update(
                consumed_weight=models.F('consumed_weight') + weight
            )

        # 4. 处理常规映射 (产出 - CVN精品)
        for field_name, inventory_key in self.INVENTORY_MAPPING.items():
            current_val = getattr(self, field_name, 0) or 0
            old_val = getattr(old_instance, field_name, 0) or 0 if old_instance else 0

            diff = current_val - old_val

            if diff != 0:
                try:
                    inv = Inventory.objects.get(key=inventory_key)
                    # 产出字段：增加库存
                    inv.quantity += diff
                    inv.save()

                    InventoryLog.objects.create(
                        inventory=inv,
                        action_type='production',
                        change_amount=diff,
                        quantity_after=inv.quantity,
                        note=f"生产批次 {self.batch_no} 自动产出 ({field_name})"
                    )
                except Inventory.DoesNotExist:
                    pass

        # 5. 真正保存
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        """
        删除逻辑：
        1. 归还源头批次的 consumed_weight。
        2. 归还 Inventory 表中的 CVN粗品库存。
        3. 扣减 Inventory 表中的 CVN精品库存 (回滚产出)。
        """
        # 1. 归还源头批次
        for item in self.input_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVNSynthesis.objects.filter(batch_no=batch_no).update(
                consumed_weight=models.F('consumed_weight') - weight
            )

        # 2. 归还 Inventory 表中的 CVN粗品库存 (相当于把消耗的加回去)
        current_input_total = 0
        for item in self.input_sources:
            current_input_total += float(item.get('use_weight', 0))

        if current_input_total > 0:
            try:
                inv_crude = Inventory.objects.get(key=constants.KEY_INTER_CVN_CRUDE)
                inv_crude.quantity += current_input_total
                inv_crude.save()

                InventoryLog.objects.create(
                    inventory=inv_crude,
                    action_type='correction',  # 删除操作视为修正
                    change_amount=current_input_total,
                    quantity_after=inv_crude.quantity,
                    note=f"删除批次 {self.batch_no} 回滚消耗"
                )
            except Inventory.DoesNotExist:
                pass

        # 3. 扣减 Inventory 表中的 CVN精品库存 (回滚产出)
        if self.output_weight > 0:
            try:
                inv_pure = Inventory.objects.get(key=constants.KEY_INTER_CVN_PURE)
                inv_pure.quantity -= self.output_weight
                inv_pure.save()

                InventoryLog.objects.create(
                    inventory=inv_pure,
                    action_type='correction',
                    change_amount=-self.output_weight,
                    quantity_after=inv_pure.quantity,
                    note=f"删除批次 {self.batch_no} 回滚产出"
                )
            except Inventory.DoesNotExist:
                pass

        super().delete(*args, **kwargs)
