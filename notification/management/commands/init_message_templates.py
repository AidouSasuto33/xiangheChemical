from django.core.management.base import BaseCommand
from notification.models import MessageTemplate

class Command(BaseCommand):
    help = '初始化常用的工单消息模板数据'

    def handle(self, *args, **options):
        templates = [
            {
                "code": "status_change_running",
                "name": "工单进入生产状态",
                "title_template": "【生产开始】{workshop} - {batch_no}",
                "content_template": "工单 {batch_no} 已由 {actor} 启动，目前处于: '{new_status}' 阶段。"
            },
            {
                "code": "status_change_completed",
                "name": "工单生产完成",
                "title_template": "【生产完成】{workshop} - {batch_no}",
                "content_template": "工单 {batch_no} 已由 {actor} 标记为: '{new_status}'，请相关人员核验。"
            },
            {
                "code": "status_change_abnormal",
                "name": "工单触发异常",
                "title_template": "【⚠️ 生产异常】{workshop} - {batch_no}",
                "content_template": "警报：工单 {batch_no} 发生异常！操作人：{actor}。当前状态: '{new_status}'。请立即处理！"
            }
        ]

        count = 0
        for t_data in templates:
            obj, created = MessageTemplate.objects.update_or_create(
                code=t_data['code'],
                defaults=t_data
            )
            if created:
                count += 1
                self.stdout.write(self.style.SUCCESS(f"成功创建模板: {t_data['name']}"))
            else:
                self.stdout.write(self.style.WARNING(f"已更新模板: {t_data['name']}"))

        self.stdout.write(self.style.SUCCESS(f"模板初始化完成，共新增 {count} 个模板。"))