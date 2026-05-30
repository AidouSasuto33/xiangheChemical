from django.contrib import admin
from django.utils.html import format_html
from .models.inventory import Inventory
from .models.audit import InventoryLog, CostConfigLog
from .models.cost_config import CostConfig

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'quantity', 'unit', 'category', 'key']
    search_fields = ['name', 'key']
    list_filter = ['category']
    list_editable = ['quantity']
    ordering = ['category', 'key']

@admin.register(CostConfig)
class CostConfigAdmin(admin.ModelAdmin):
    list_display = ['label', 'cost_price', 'sale_price', 'unit', 'category', 'key', 'updated_at']
    list_editable = ['cost_price', 'sale_price']
    search_fields = ['label', 'key']
    list_filter = ['category']
    readonly_fields = ['key']

    def save_model(self, request, obj, form, change):
        if change:
            try:
                old_obj = CostConfig.objects.get(pk=obj.pk)
                if old_obj.cost_price != obj.cost_price or old_obj.sale_price != obj.sale_price:
                    CostConfigLog.objects.create(
                        config=obj,
                        operator=request.user,
                        old_cost_price=old_obj.cost_price,
                        new_cost_price=obj.cost_price,
                        old_sale_price=old_obj.sale_price,
                        new_sale_price=obj.sale_price
                    )
            except CostConfig.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)

@admin.register(CostConfigLog)
class CostConfigLogAdmin(admin.ModelAdmin):
    list_display = ['changed_at', 'config_label', 'old_cost_price', 'new_cost_price', 'old_sale_price', 'new_sale_price', 'operator']
    list_filter = ['operator']
    search_fields = ['config__label']
    readonly_fields = [field.name for field in CostConfigLog._meta.fields]

    def config_label(self, obj):
        return obj.config.label
    config_label.short_description = "配置项"

@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'inventory_name', 'action_type_colored', 'change_amount', 'quantity_after', 'operator']
    list_filter = ['action_type', 'inventory__category']
    search_fields = ['inventory__name', 'note']
    readonly_fields = [field.name for field in InventoryLog._meta.fields]

    def inventory_name(self, obj):
        return obj.inventory.name
    inventory_name.short_description = "物料"

    def action_type_colored(self, obj):
        colors = {
            'purchase': 'green',
            'sale': 'blue',
            'production': 'orange',
            'correction': 'red',
            'safe_stock': 'purple',
        }
        color = colors.get(obj.action_type, 'black')
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_action_type_display()
        )
    action_type_colored.short_description = "操作类型"
