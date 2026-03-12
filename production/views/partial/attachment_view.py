from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from django.views import View
from django.http import JsonResponse

from production.models.partial import Attachment


class AttachmentUploadView(LoginRequiredMixin, View):
    """
    处理通用附件上传的 Class-Based View
    接收前端 Dropzone.js 传来的图片及 GenericForeignKey 参数
    """

    def post(self, request, *args, **kwargs):
        image = request.FILES.get('image')
        model_name = request.POST.get('model_name')
        object_id = request.POST.get('object_id')
        attachment_type = request.POST.get('attachment_type')

        # 基础数据校验
        if not all([image, model_name, object_id, attachment_type]):
            return JsonResponse({'error': '上传参数不完整，请刷新页面重试'}, status=400)

        try:
            # 动态解析 ContentType
            content_type = ContentType.objects.get(app_label='production', model=model_name)

            # 创建附件记录（此时底层的 save() 会被触发，自动在内存中生成并保存 WebP 缩略图）
            attachment = Attachment.objects.create(
                content_type=content_type,
                object_id=object_id,
                image=image,
                attachment_type=attachment_type,
                uploaded_by=request.user
            )

            # 返回给前端的成功响应，带上新生成的缩略图路径
            return JsonResponse({
                'message': '上传成功',
                'attachment_id': attachment.id,
                'file_url': attachment.image.url,
                'thumbnail_url': attachment.thumbnail.url if attachment.thumbnail else ''
            })

        except ContentType.DoesNotExist:
            return JsonResponse({'error': f'系统级错误：未找到模型 {model_name}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'服务器保存失败: {str(e)}'}, status=500)


class AttachmentManageView(LoginRequiredMixin, View):
    """
    负责展示和管理附件的视图 (提供 HTML 片段)
    """

    def get(self, request, *args, **kwargs):
        model_name = request.GET.get('model_name')
        object_id = request.GET.get('object_id')

        # 获取对应的 ContentType
        content_type = ContentType.objects.get(app_label='production', model=model_name)

        # 获取该工单下的所有附件，修正排序字段为 uploaded_at
        attachments = Attachment.objects.filter(
            content_type=content_type,
            object_id=object_id
        ).select_related('uploaded_by', 'changed_by').order_by('-uploaded_at')

        # 严格按照 AttachmentType 枚举进行分类打包 (INCIDENT 修正为 ABNORMAL)
        data = {
            'qa': attachments.filter(attachment_type='QA'),
            'abnormal': attachments.filter(attachment_type='ABNORMAL'),
            'other': attachments.filter(attachment_type='OTHER'),
            'invalid': attachments.filter(attachment_type='INVALID'),
        }

        # 渲染局部 HTML 返回给前端弹窗
        html = render_to_string('production/procedure/partials/_attachment_list_content.html', data, request=request)
        return JsonResponse({'html': html})

    def post(self, request, *args, **kwargs):
        """
        修改附件分类 (修正/废弃)
        """
        attachment_id = request.POST.get('attachment_id')
        new_type = request.POST.get('new_type')

        attachment = get_object_or_404(Attachment, id=attachment_id)

        # 审计留痕：更新类型并记录操作人
        attachment.attachment_type = new_type
        attachment.changed_by = request.user
        # changed_at 会因为模型层设置了 auto_now=True 而自动更新
        attachment.save()

        return JsonResponse({'status': 'success', 'message': '分类已更新'})