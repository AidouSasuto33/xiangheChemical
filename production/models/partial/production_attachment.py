from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
import os
from uuid import uuid4
from django.utils import timezone


def attachment_upload_path(instance, filename):
    """
    动态生成图片上传路径。
    格式: attachments/应用名/表名/YYYY/MM/UUID_原文件名
    例如: attachments/production/cvnsynthesis/2026/03/a1b2c3d4_quality.jpg
    """
    ext = filename.split('.')[-1]
    # 结合 UUID 重命名文件，彻底避免同名覆盖问题
    new_filename = f"{uuid4().hex}.{ext}"

    app_label = instance.content_type.app_label
    model_name = instance.content_type.model
    now = timezone.now()

    return f"attachments/{app_label}/{model_name}/{now.strftime('%Y/%m')}/{new_filename}"


class ProductionAttachment(models.Model):
    """
    通用生产附件表（万能插座）
    """

    class AttachmentType(models.TextChoices):
        QA = 'QA', '质检/完工证明'
        ABNORMAL = 'ABNORMAL', '异常/事故现场'
        OTHER = 'OTHER', '其他辅助说明'

    # === 1. 万能插座 (Generic Foreign Key) ===
    # 指向 Django 的 ContentType 表，记录这是哪种工单（如 CVNSynthesis）
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        verbose_name="关联表类型"
    )
    # 记录具体是那张工单的 ID
    object_id = models.PositiveIntegerField(verbose_name="关联数据ID")
    # Django 提供的快捷访问对象，不实际生成数据库字段
    content_object = GenericForeignKey('content_type', 'object_id')

    # === 2. 核心业务字段 ===
    image = models.ImageField(
        upload_to=attachment_upload_path,
        verbose_name="附件图片",
        help_text="支持上传生产现场、质检结果或异常情况的照片"
    )

    attachment_type = models.CharField(
        max_length=20,
        choices=AttachmentType.choices,
        default=AttachmentType.OTHER,
        verbose_name="附件类型标签"
    )

    # === 3. 审计与追踪字段 ===
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,  # 保护模式：如果人员离职，只禁用账号，不级联删除他传的图
        verbose_name="上传人"
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="上传时间"
    )

    is_deleted = models.BooleanField(
        default=False,
        verbose_name="软删除标记",
        help_text="出于化工合规与审计要求，附件不可物理删除。设为 True 仅在前端隐藏。"
    )

    class Meta:
        verbose_name = "生产附件"
        verbose_name_plural = "生产附件"
        # 建立联合索引，极大提升查询某个特定工单下所有附件的速度
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"[{self.get_attachment_type_display()}] ID:{self.object_id} - {self.uploaded_at.strftime('%Y-%m-%d')}"