import os
from uuid import uuid4
from io import BytesIO
from PIL import Image

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.files.base import ContentFile


def attachment_upload_path(instance, filename):
    """动态生成原图上传路径"""
    ext = filename.split('.')[-1].lower()
    new_filename = f"{uuid4().hex}.{ext}"
    app_label = instance.content_type.app_label
    model_name = instance.content_type.model
    now = timezone.now()
    return f"{app_label}/{model_name}/{now.strftime('%Y/%m')}/{new_filename}"


def thumbnail_upload_path(instance, filename):
    """动态生成缩略图上传路径 (专门存放在 thumbnails 子目录下)"""
    ext = filename.split('.')[-1].lower()
    new_filename = f"{uuid4().hex}_thumb.{ext}"
    app_label = instance.content_type.app_label
    model_name = instance.content_type.model
    now = timezone.now()
    return f"{app_label}/{model_name}/{now.strftime('%Y/%m')}/thumbnails/{new_filename}"


class Attachment(models.Model):
    """
    通用生产附件表（万能插座 + 双图引擎）
    """

    class AttachmentType(models.TextChoices):
        QA = 'QA', '质检/完工证明'
        ABNORMAL = 'ABNORMAL', '异常/事故现场'
        OTHER = 'OTHER', '其他辅助说明'
        INVALID = 'INVALID', '已废弃/错图'  # 👈 新增：用于审计追踪，物理不删，逻辑作废

    # === 1. 万能插座 (Generic Foreign Key) ===
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, verbose_name="关联表类型")
    object_id = models.PositiveIntegerField(verbose_name="关联数据ID")
    content_object = GenericForeignKey('content_type', 'object_id')

    # === 2. 核心业务字段 (原图 + 缩略图) ===
    image = models.ImageField(upload_to=attachment_upload_path, verbose_name="附件原图",
                              help_text="支持上传生产现场、质检结果或异常情况的照片")

    # 👈 新增：缩略图字段
    thumbnail = models.ImageField(upload_to=thumbnail_upload_path, null=True, blank=True, verbose_name="缩略图",
                                  help_text="系统自动生成的WebP极速加载图")

    attachment_type = models.CharField(max_length=20, choices=AttachmentType.choices, default=AttachmentType.OTHER,
                                       verbose_name="附件类型标签")

    # === 3. 审计与追踪字段 ===
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, verbose_name="上传人")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="上传时间")

    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name='modified_attachments', verbose_name="最后修改人")
    changed_at = models.DateTimeField(auto_now=True, null=True, blank=True, verbose_name="最后修改时间")  # 修正了拼写

    class Meta:
        verbose_name = "生产附件"
        verbose_name_plural = "生产附件"
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"[{self.get_attachment_type_display()}] ID:{self.object_id} - {self.uploaded_at.strftime('%Y-%m-%d')}"

    def save(self, *args, **kwargs):
        """
        重写 save 方法：在保存原图的同时，拦截并自动生成 WebP 格式的极度压缩缩略图
        """
        # 如果是第一次创建（即没有主键），并且上传了图片，则生成缩略图
        if not self.pk and self.image:
            self.make_thumbnail()

        super().save(*args, **kwargs)

    def make_thumbnail(self):
        """核心工艺：生成缩略图"""
        # 1. 用 Pillow 打开内存中的原图
        img = Image.open(self.image)

        # 2. 统一转换为 RGB 模式（防范 RGBA 的 PNG 转存时报错）
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        # 3. 核心压缩：限制最大宽高为 300x300，Pillow 会自动保持比例
        img.thumbnail((300, 300), Image.Resampling.LANCZOS)

        # 4. 在内存中创建一个缓冲管道
        thumb_io = BytesIO()

        # 5. 将图片以 WebP 格式（体积最小）保存到内存管道中，画质 80 完全够缩略图用
        img.save(thumb_io, format='WEBP', quality=80)
        thumb_io.seek(0)

        # 6. 构造新的缩略图文件名
        original_name = os.path.basename(self.image.name)
        name_without_ext = os.path.splitext(original_name)[0]
        thumb_filename = f"{name_without_ext}.webp"

        # 7. 将内存管道里的数据打包成 Django 文件对象，并赋值给 thumbnail 字段
        # 注意：save=False 是为了避免在模型保存前意外触发死循环或多余的 I/O
        self.thumbnail.save(thumb_filename, ContentFile(thumb_io.read()), save=False)