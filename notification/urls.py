# notification/urls.py
from django.urls import path
from . import views

app_name = 'notification'

urlpatterns = [
    # 主页小铃铛弹窗 AJAX API 路由
    path('api/unread/', views.get_unread_notifications, name='api_unread'),
    path('api/mark-all-read/', views.mark_all_read, name='api_mark_all_read'),

    # 消息中转与跳转路由
    path('read/<int:pk>/', views.mark_as_read_and_redirect, name='read_and_redirect'),

    # 消息中心主页
    path('', views.notification_index, name='index'),

    # 单条操作 API
    path('api/read-single/', views.mark_single_read, name='api_mark_single_read'),
    path('api/delete/', views.delete_notification, name='api_delete'),
]