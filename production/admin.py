from django.contrib import admin
from django.utils.html import format_html
from .models.inventory import Inventory
from .models.audit import InventoryLog, CostConfigLog
from .models.core import CostConfig
from .models.cvn_synthesis import CVNSynthesis
from .models.cvn_distillation import CVNDistillation
from .models.cva_synthesis import CVASynthesis
from .models.cvc_synthesis import CVCSynthesis
from .models.cvc_export import CVCExport


# =========================================================
# 1. 基础设施 (Inventory, Config, Audit)
# =========================================================

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'quantity', 'unit', 'category', 'key', 'updated_at']
    search_fields = ['name', 'key']
    list_filter = ['category']
    # 允许在列表页直接修改库存，方便调试 (上线时可去掉)
    list_editable = ['quantity']
    ordering = ['category', 'key']


@admin.register(CostConfig)
class CostConfigAdmin(admin.ModelAdmin):
    list_display = ['label', 'price', 'unit', 'category', 'key']
    list_editable = ['price']
    search_fields = ['label']


@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'inventory_name', 'action_type_colored', 'change_amount', 'quantity_after',
                    'operator']
    list_filter = ['action_type', 'inventory__category']
    search_fields = ['inventory__name', 'note']
    readonly_fields = [field.name for field in InventoryLog._meta.fields]  # 全只读

    def inventory_name(self, obj):
        return obj.inventory.name

    inventory_name.short_description = "物料"

    def action_type_colored(self, obj):
        """给操作类型上色"""
        colors = {
            'purchase': 'green',
            'sale': 'blue',
            'production': 'orange',
            'correction': 'red',
        }
        color = colors.get(obj.action_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_type_display()
        )

    action_type_colored.short_description = "操作类型"


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
    list_display = ['batch_no', 'status_badge', 'crude_weight', 'remaining_weight', 'test_time']
    search_fields = ['batch_no']


@admin.register(CVNDistillation)
class CVNDistillationAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'status_badge', 'input_total_weight', 'output_weight', 'remaining_weight']
    search_fields = ['batch_no']


@admin.register(CVASynthesis)
class CVASynthesisAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'status_badge', 'input_total_weight', 'crude_weight', 'remaining_weight']
    search_fields = ['batch_no']


@admin.register(CVCSynthesis)
class CVCSynthesisAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'product_weight', 'remaining_weight', 'created_at']
    # CVC 成品主要看剩余量，状态次要
    search_fields = ['batch_no']


@admin.register(CVCExport)
class CVCExportAdmin(BaseProductionAdmin):
    list_display = ['batch_no', 'input_total_weight', 'premium_weight', 'created_at']
    search_fields = ['batch_no']