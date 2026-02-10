from django.contrib import admin
from django.utils.html import format_html
from .models import Inventory, InventoryLog, CostConfig, CostConfigLog

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    # Inventory 模型中没有 updated_at 字段，已移除
    list_display = ['name', 'quantity', 'unit', 'category', 'key']
    search_fields = ['name', 'key']
    list_filter = ['category']
    list_editable = ['quantity']
    ordering = ['category', 'key']

@admin.register(CostConfig)
class CostConfigAdmin(admin.ModelAdmin):
    list_display = ['label', 'price', 'unit', 'category', 'key', 'updated_at']
    list_editable = ['price']
    search_fields = ['label', 'key']
    list_filter = ['category']
    readonly_fields = ['key']

    def save_model(self, request, obj, form, change):
        if change:
            try:
                old_obj = CostConfig.objects.get(pk=obj.pk)
                old_price = old_obj.price
                new_price = obj.price
                if old_price != new_price:
                    # CostConfigLog 没有 reason 字段，已移除
                    CostConfigLog.objects.create(
                        config=obj,
                        operator=request.user,
                        old_price=old_price,
                        new_price=new_price
                    )
            except CostConfig.DoesNotExist:
                pass
        super().save_model(request, obj, form, change)

@admin.register(CostConfigLog)
class CostConfigLogAdmin(admin.ModelAdmin):
    # CostConfigLog 使用 changed_at 而不是 created_at
    # CostConfigLog 没有 reason 字段
    list_display = ['changed_at', 'config_label', 'old_price', 'new_price', 'operator']
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