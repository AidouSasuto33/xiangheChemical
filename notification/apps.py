from django.apps import AppConfig

class NotificationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notification'
    verbose_name = '消息通知系统'

    def ready(self):
        # Django 启动完毕后，导入并注册信号接收器
        import notification.signals.procedure_notification_handlers