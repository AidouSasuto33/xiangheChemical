import logging
from django.dispatch import receiver
from django.urls import reverse
from production.signals import post_procedure_state_change
from notification.models import Notification, MessageTemplate
from system.models import Employee

logger = logging.getLogger(__name__)

@receiver(post_procedure_state_change)
def handle_procedure_status_change(sender, instance, old_status, new_status, user, **kwargs):
    """
    接收工单状态变更信号，渲染模板并分发通知给相关车间的人员。
    """
    try:
        # 1. 动态确定模板编码 (例如: status_change_in_progress, status_change_exception)
        # 这里假设 new_status 是类似 'in_progress', 'completed' 的字符串代码
        template_code = f"status_change_{new_status}"
        template = MessageTemplate.objects.filter(code=template_code).first()

        # 定义渲染用的上下文变量
        context = {
            'batch_number': getattr(instance, 'batch_number', '未知批次'),
            'workshop': getattr(instance, 'workshop', '未知车间'),
            'actor': user.username if user else '系统',
            'old_status': old_status,
            'new_status': getattr(instance, 'get_status_display', lambda: new_status)(),
        }

        # 2. 准备通知的内容与级别
        if template:
            title = template.title_template.format(**context)
            content = template.content_template.format(**context)
        else:
            # 后备方案：如果没有在数据库配置对应模板，使用通用文案
            logger.warning(f"缺少消息模板: {template_code}，使用默认文案。")
            title = f"工单状态更新: {context['new_status']}"
            content = f"工单 {context['batch_number']} ({context['workshop']}) 的状态已由 {context['actor']} 更改为 {context['new_status']}。"

        # 根据状态判定消息级别 (异常状态走 danger，完成走 success，其他走 info)
        level = 'info'
        notice_type = 'status'
        if new_status == 'exception':  # 根据你们实际定义的状态常量调整
            level = 'danger'
            notice_type = 'exception'
        elif new_status == 'completed':
            level = 'success'

        # 3. 生成工单的目标链接 (target_url)
        # 这里使用 Django 规范的 get_absolute_url，如果模型没定义，先留空
        target_url = ""
        if hasattr(instance, 'get_absolute_url'):
            target_url = instance.get_absolute_url()
        else:
            # 作为占位符，后续可以在业务模型里补齐 get_absolute_url 方法
            target_url = f"/production/detail/{instance.pk}/"

        # 4. 寻找接收人 (重点：利用咱们刚设计好的多对多关系)
        recipients = []
        if hasattr(instance, 'workshop') and instance.workshop:
            # 找到管辖该工单所在车间的所有员工
            employees = Employee.objects.filter(workshops=instance.workshop).select_related('user')
            recipients = [emp.user for emp in employees if emp.user]

        # 5. 批量生成通知记录 (Bulk Create 提升性能)
        if recipients:
            notifications = [
                Notification(
                    recipient=recipient,
                    actor=user,
                    level=level,
                    notice_type=notice_type,
                    title=title,
                    content=content,
                    target_url=target_url
                )
                for recipient in recipients
            ]
            Notification.objects.bulk_create(notifications)

    except Exception as e:
        logger.error(f"处理工单状态变更通知失败: {e}", exc_info=True)