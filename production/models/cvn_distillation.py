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

    # =========================================================
    # 4. 固废 (Waste)
    # =========================================================
    residue_weight = models.FloatField("釜残重量(kg)", default=0, help_text="危废处理成本依据")

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
        """
        # 1. 自动生成批号
        if not self.id and not self.batch_no:
            self.batch_no = generate_batch_number(CVNDistillation, "CVN-JING")

        # 2. 库存处理逻辑
        # A. 如果是修改现有的记录：先“归还”旧的库存
        if self.pk:
            old_instance = CVNDistillation.objects.get(pk=self.pk)
            for item in old_instance.input_sources:
                batch_no = item.get('batch_no')
                weight = float(item.get('use_weight', 0))
                # 归还库存 (consumed_weight 减去)
                CVNSynthesis.objects.filter(batch_no=batch_no).update(
                    consumed_weight=models.F('consumed_weight') - weight
                )

        # B. 扣减新的库存
        for item in self.input_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            # 扣减库存 (consumed_weight 加上)
            CVNSynthesis.objects.filter(batch_no=batch_no).update(
                consumed_weight=models.F('consumed_weight') + weight
            )

        # 3. 真正保存
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        """
        删除逻辑：
        删除记录时，必须把库存“还回去”。
        """
        for item in self.input_sources:
            batch_no = item.get('batch_no')
            weight = float(item.get('use_weight', 0))
            CVNSynthesis.objects.filter(batch_no=batch_no).update(
                consumed_weight=models.F('consumed_weight') - weight
            )
        super().delete(*args, **kwargs)