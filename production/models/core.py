# Django基础ORM管理
from django.db import models
# 引入 Postgres 特有的 ArrayField (虽然 JSONField 更通用，但这里用 JSON 兼容性更好)
from django.db.models import JSONField
# django用户管理库
from django.contrib.auth.models import User

from core.constants.procedure_status import ProcedureState
from django.urls import reverse
from .kettle import Kettle

# ==========================================
# 1. 抽象基类 (BaseProductionStep) - 重构版
# ==========================================

class BaseProductionStep(models.Model):
    """
    生产工段基类 (Abstract)
    核心逻辑变更：
    1. 时间：由单一 Date 改为 Start/End 手动选择。
    2. 劳务：废弃固定字段，改用 JSON 灵活存储 "工种+人数+单位量"。
    3. 灵活性：允许部分步骤为空。
    """

    # --- 1. 核心追踪 ---
    batch_no = models.CharField("生产批号", max_length=50, unique=True)
    
    status = models.CharField(
        "状态",
        max_length=20,
        choices=ProcedureState.choices,
        default=ProcedureState.NEW,
        db_index=True,
        help_text="生产状态流转：新建 -> 生产中(锁原料) -> 完工(入成品)"
    )

    kettle = models.ForeignKey(
        Kettle,
        on_delete=models.PROTECT,
        related_name='%(class)s_related',
        verbose_name="生产设备",
        help_text="该生产步骤所使用的具体釜皿/设备",
        null=True,
        blank=True
    )

    # --- 2. 时间管理 ---
    # 不使用 auto_now，完全由文员手动选择日历
    start_time = models.DateTimeField("开始时间")
    end_time = models.DateTimeField("结束时间", null=True, blank=True)

    # --- 3. 劳务成本记录 (核心变更) ---
    # 数据结构示例：
    # [
    #   {"role_key": "wage_input", "count": 2, "amount": 1.5, "note": "投料"},
    #   {"role_key": "wage_waste", "count": 1, "amount": 1.0, "note": "废水处理"}
    # ]
    labor_records = JSONField(
        "人工工时记录",
        default=list,
        blank=True,
        help_text="格式：[{工种Key, 人数, 耗时/次数}]"
    )

    # --- 4. 辅助信息 ---
    #TODO 备注与操作数据结构改为LIST，每次操作都留痕
    operator = models.ForeignKey(
        User,
        on_delete=models.PROTECT,  # 关键：如果该账号有数据，禁止物理删除，强迫管理员改用“禁用”
        verbose_name="记录员",
        help_text="自动关联当前登录账号，不可为空"
    )
    remarks = models.TextField("备注", blank=True, null=True)

    # 系统自动记录的修改时间（用于审计，不用于业务）
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("最后更新", auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-start_time']

    def __str__(self):
        return f"{self.batch_no} ({self.start_time.strftime('%Y-%m-%d')})"

    @property
    def duration_hours(self):
        """辅助计算：总耗时（小时）"""
        if self.end_time and self.start_time:
            delta = self.end_time - self.start_time
            return round(delta.total_seconds() / 3600, 1)
        return 0

    def get_absolute_url(self):
        """动态生成工单更新页面的 URL。"""
        #TODO 项目正式上线时，将返回的domain放在DJango Site中去。
        return "127.0.0.1:8000" + reverse(f'production:{getattr(self, 'url_name_base')}', kwargs={'pk': self.pk})
