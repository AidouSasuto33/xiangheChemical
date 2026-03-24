from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords


class LaborRecord(models.Model):
    """
    人工成本投入记录表
    作为独立的“事实表”，通过 batch_no 与各生产工单软关联。
    专为极速查询和 Echarts 财务/工时数据可视化设计。
    """

    # --- 1. 核心关联与分类 (用于高频聚合查询) ---
    batch_no = models.CharField(
        "生产批号",
        max_length=21,
        db_index=True,
        help_text="关联具体工单的批号，用于钻取明细"
    )

    procedure_type = models.CharField(
        "工艺类别",
        max_length=7,
        db_index=True,
        help_text="工艺标识（如 CVN_SYN, CVN_DIS），极大地提升按工艺分类的报表查询性能"
    )

    # --- 2. 费用项配置 ---
    # 跨 App 外键关联，限制只能选择“人工成本”类别的配置项
    cost_config = models.ForeignKey(
        'inventory.CostConfig',
        on_delete=models.PROTECT,
        verbose_name="工种/费用项",
        limit_choices_to={'category': 'labor'}
    )

    # --- 3. 投入明细 ---
    worker_count = models.PositiveIntegerField("投入人数", default=1)
    work_hours = models.DecimalField("投入工时", max_digits=6, decimal_places=2, default=0)

    cost_snapshot = models.DecimalField(
        "单价快照(元)",
        max_digits=10,
        decimal_places=2,
        help_text="保存操作当时的单价，防止全局调价破坏历史财务数据"
    )

    # --- 4. 统计时间维度 ---
    # 添加 db_index=True，因为陈总的图表肯定要按日/周/月/季/年进行 Where 和 Group By 筛选
    record_date = models.DateField(
        "记录日期",
        default=timezone.now,
        db_index=True,
        help_text="用于时间序列报表统计的核心字段"
    )

    # --- 5. 自动审计追踪 ---
    history = HistoricalRecords()

    class Meta:
        verbose_name = "人力投入记录"
        verbose_name_plural = verbose_name
        # 默认按记录日期倒序，同日期的按ID倒序
        ordering = ['-record_date', '-id']

    def __str__(self):
        return f"[{self.procedure_type}] {self.batch_no} - {self.cost_config.label} ({self.worker_count}人*{self.work_hours}H)"

    @property
    def total_cost(self):
        """辅助计算当前记录的总成本 (金额)"""
        return self.worker_count * self.work_hours * self.cost_snapshot