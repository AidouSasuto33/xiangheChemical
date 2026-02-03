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



# production/admin.py

# ... (保持上面的 imports 不变) ...

# =========================================================
# 1. 基础设施 (Inventory, Config, Audit)
# =========================================================

# ... (InventoryAdmin 保持不变) ...

@admin.register(CostConfig)
class CostConfigAdmin(admin.ModelAdmin):
    list_display = ['label', 'price', 'unit', 'category', 'key', 'updated_at']
    list_editable = ['price']
    search_fields = ['label', 'key']
    list_filter = ['category']
    readonly_fields = ['key'] # 防止手滑改掉关键Key

    # 【核心逻辑】重写保存方法，拦截修改动作
    def save_model(self, request, obj, form, change):
        """
        request: 当前请求（包含 logged-in user）
        obj: 修改后的对象（新价格）
        change: Boolean, True表示修改，False表示新建
        """
        # 1. 如果是修改操作 (Change)，记录日志
        if change:
            try:
                # 获取数据库里的旧对象
                old_obj = CostConfig.objects.get(pk=obj.pk)
                old_price = old_obj.price
                new_price = obj.price

                # 只有价格变了才记录
                if old_price != new_price:
                    CostConfigLog.objects.create(
                        config=obj,
                        operator=request.user,  # 只有在Admin里才能轻松拿到这个！
                        old_price=old_price,
                        new_price=new_price,
                        reason="管理员后台修改"
                    )
            except CostConfig.DoesNotExist:
                pass

        # 2. 执行正常的保存
        super().save_model(request, obj, form, change)


# 【新增】注册 Config 审计日志，供查看
@admin.register(CostConfigLog)
class CostConfigLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'config_label', 'old_price', 'new_price', 'operator', 'reason']
    list_filter = ['operator']
    search_fields = ['config__label', 'reason']
    readonly_fields = [field.name for field in CostConfigLog._meta.fields] # 全只读

    def config_label(self, obj):
        return obj.config.label
    config_label.short_description = "配置项"

# ... (InventoryLogAdmin 及后续代码保持不变) ...


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