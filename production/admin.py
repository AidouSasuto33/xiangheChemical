from django.contrib import admin
from django.utils.html import format_html
from .models.cvn_synthesis import CVNSynthesis
from .models.cvn_distillation import CVNDistillation
from .models.cva_synthesis import CVASynthesis
from .models.cvc_synthesis import CVCSynthesis
from .models.cvc_export import CVCExport
from .models.kettle import Kettle
from simple_history.admin import SimpleHistoryAdmin
from .models.labor_record import LaborRecord


# =========================================================
# 2. 工艺流程 (Step 1 - Step 5)
# =========================================================

class BaseProductionAdmin(admin.ModelAdmin):
    """所有工艺单的通用 Admin 配置"""
    list_per_page = 20
    readonly_fields = ['batch_no', 'consumed_weight']  # 批号和消耗量由系统控制，禁止手改
    ordering = ['-created_at']

    def status_badge(self, obj):
        """将 status_label 渲染为彩色徽章"""
        status = obj.status_label
        color_map = {
            "🟢 全新待领": "#28a745",  # Green
            "🟡 部分领用": "#ffc107",  # Yellow
            "⚫ 耗尽归档": "#6c757d",  # Grey
            "异常批次": "#dc3545",  # Red
        }
        bg_color = color_map.get(status, "#000")
        text_color = "#000" if status == "🟡 部分领用" else "#fff"

        return format_html(
            '<span style="background-color: {}; color: {}; padding: 3px 8px; border-radius: 4px;">{}</span>',
            bg_color, text_color, status
        )

    status_badge.short_description = "状态"


@admin.register(CVNSynthesis)
class CVNSynthesisAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'status_badge', 'cvn_syn_crude_weight', 'remaining_weight', 'test_time']
    search_fields = ['batch_no']


@admin.register(CVNDistillation)
class CVNDistillationAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'status_badge', 'input_total_cvn_weight', 'cvn_dis_crude_weight', 'remaining_weight']
    search_fields = ['batch_no']


@admin.register(CVASynthesis)
class CVASynthesisAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'status_badge', 'input_total_cvc_dis_weight', 'cva_crude_weight', 'remaining_weight']
    search_fields = ['batch_no']


@admin.register(CVCSynthesis)
class CVCSynthesisAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'status_badge', 'input_total_cva_weight','cvc_syn_crude_weight', 'remaining_weight']
    # CVC 成品主要看剩余量，状态次要
    search_fields = ['batch_no']


@admin.register(CVCExport)
class CVCExportAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'status_badge', 'input_total_cvc_weight', 'cvc_dis_crude_weight', 'remaining_weight']
    search_fields = ['batch_no']


@admin.register(Kettle)
class KettleAdmin(admin.ModelAdmin):
    list_display = ('name', 'workshop', 'status', 'capacity', 'supported_processes', 'current_batch_no')
    list_filter = ('status', 'workshop', 'supported_processes')
    search_fields = ('name', 'current_batch_no')
    list_editable = ('status',)  # 允许在列表页直接改状态 (方便快速测试)

    def status_badge(self, obj):
        """显示带颜色的状态"""
        from django.utils.html import format_html
        colors = {
            'idle': 'green',
            'running': 'red',
            'to_clean': 'orange',
            'maintenance': 'gray'
        }
        color = colors.get(obj.status, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display()
        )

    status_badge.short_description = "状态"


@admin.register(LaborRecord)
class LaborRecordAdmin(SimpleHistoryAdmin):
    """
    人力投入记录后台管理
    集成 SimpleHistoryAdmin 以便在后台审计每一笔工时的修改轨迹
    """
    # 列表页展示字段：批号、工艺、工种、人数、工时、计算后的总金额、记录日期
    list_display = [
        'batch_no', 'procedure_type', 'cost_config',
        'worker_count', 'work_hours', 'record_date'
    ]

    # 右侧筛选器：支持按工艺类别、日期、工种进行快速过滤
    list_filter = ['procedure_type', 'record_date', 'cost_config']

    # 搜索框：支持按批号或工种名称模糊搜索
    search_fields = ['batch_no', 'cost_config__label']

    # 详情页字段分组
    fieldsets = (
        ('核心关联', {
            'fields': ('batch_no', 'procedure_type', 'record_date')
        }),
        ('投入明细', {
            'fields': ('cost_config', 'worker_count', 'work_hours', 'cost_snapshot')
        }),
    )

    # 单价快照设为只读，保证审计的严肃性（不可在后台随意篡改快照价格）
    readonly_fields = ['cost_snapshot']
