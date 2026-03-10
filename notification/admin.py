from django.contrib import admin
from .models import MessageTemplate, Notification


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'title_template', 'sms_template_code')
    search_fields = ('name', 'code')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notice_type', 'level', 'title', 'is_read', 'created_at')
    list_filter = ('notice_type', 'level', 'is_read', 'created_at')
    search_fields = ('recipient__username', 'title', 'content')
    readonly_fields = ('created_at', 'read_at')  # 记录类数据建议设为只读以防篡改

    # 按照创建时间倒序排列
    ordering = ('-created_at',)