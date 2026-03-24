# notification/urls.py
from django.urls import path
from . import views

app_name = 'notification'

urlpatterns = [
    # 之后我们用来查看“所有消息”的主页路由可以放在这里
    # path('', views.NotificationListView.as_view(), name='index'),

    # AJAX API 路由
    path('api/unread/', views.get_unread_notifications, name='api_unread'),
    path('api/mark-all-read/', views.mark_all_read, name='api_mark_all_read'),
]