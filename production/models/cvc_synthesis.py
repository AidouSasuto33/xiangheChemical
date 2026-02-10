from django.db import models, transaction
from django.db.models import JSONField, F
from django.core.exceptions import ValidationError

from .core import BaseProductionStep
# 引入 Step 3 (CVA合成) 作为原料来源
from .cva_synthesis import CVASynthesis
from ..utils.batch_generator import generate_batch_number
# 引入常量
from core import constants



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