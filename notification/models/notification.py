from django.db import models
from django.contrib.auth.models import User


class MessageTemplate(models.Model):
    """
    消息模板：用于灵活配置站内信和未来短信的文案
    例如：
    code: 'status_completed'
    title_template: '{workshop} - {batch_number} 生产完成'
    content_template: '工单 {batch_number} 已由 {actor} 标记为完成。'
    """
    code = models.CharField(max_length=50, unique=True, verbose_name="模板编码")
    name = models.CharField(max_length=100, verbose_name="模板名称")
    title_template = models.CharField(max_length=255, verbose_name="标题模板")
    content_template = models.TextField(verbose_name="内容模板")

    # 为未来接入阿里云/腾讯云短信预留的模板ID位
    sms_template_code = models.CharField(max_length=100, blank=True, null=True, verbose_name="短信平台模板ID")

    class Meta:
        verbose_name = "消息模板"
        verbose_name_plural = verbose_name

    def __str__(self):
        return f"{self.name} ({self.code})"


class Notification(models.Model):
    """
    具体的系统通知/站内信记录
    """
    LEVEL_CHOICES = (
        ('info', '信息'),
        ('success', '成功'),
        ('warning', '警告'),
        ('danger', '危险/异常'),
    )

    TYPE_CHOICES = (
        ('status', '工单状态变更'),
        ('exception', '生产异常'),
        ('audit', '审核提醒'),
        ('system', '系统消息'),
    )

    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name="接收人"
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='triggered_notifications',
        verbose_name="触发者"
    )

    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, default='info', verbose_name="级别")
    notice_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='status', verbose_name="类型")

    title = models.CharField(max_length=255, verbose_name="标题")
    content = models.TextField(verbose_name="内容")
    target_url = models.CharField(max_length=500, blank=True, null=True, verbose_name="跳转链接")

    is_read = models.BooleanField(default=False, verbose_name="是否已读")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="发送时间")
    read_at = models.DateTimeField(null=True, blank=True, verbose_name="阅读时间")
    sent_sms = models.BooleanField(default=False, verbose_name="是否同步发送短信")

    class Meta:
        verbose_name = "通知"
        verbose_name_plural = verbose_name
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_notice_type_display()}] {self.recipient.username} - {self.title}"

    def mark_as_read(self):
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])