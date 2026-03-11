from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.contenttypes.models import ContentType
from production.models.partial import ProductionAttachment


class ProductionAttachmentUploadView(LoginRequiredMixin, View):
    """
    处理通用附件上传的 Class-Based View
    接收前端 Dropzone.js 传来的图片及 GenericForeignKey 参数
    """

    def post(self, request, *args, **kwargs):
        # 1. 提取前端 FormData 传来的参数
        image = request.FILES.get('image')
        model_name = request.POST.get('model_name')
        object_id = request.POST.get('object_id')
        attachment_type = request.POST.get('attachment_type')

        # 基础数据校验
        if not all([image, model_name, object_id, attachment_type]):
            return JsonResponse({'error': '上传参数不完整，请刷新页面重试'}, status=400)

        try:
            # 2. 动态解析 ContentType
            # 这里固定 app_label 为 'production'，去匹配传过来的如 'cvnsynthesis'
            content_type = ContentType.objects.get(app_label='production', model=model_name)

            # 3. 创建并保存附件记录
            attachment = ProductionAttachment.objects.create(
                content_type=content_type,
                object_id=object_id,
                image=image,
                attachment_type=attachment_type,
                uploaded_by=request.user
            )

            # 返回给 Dropzone 的成功响应
            return JsonResponse({
                'message': '上传成功',
                'attachment_id': attachment.id,
                'file_url': attachment.image.url
            })

        except ContentType.DoesNotExist:
            return JsonResponse({'error': f'系统级错误：未找到模型 {model_name}'}, status=400)
        except Exception as e:
            return JsonResponse({'error': f'服务器保存失败: {str(e)}'}, status=500)