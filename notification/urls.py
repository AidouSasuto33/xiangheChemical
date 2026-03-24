# notification/urls.py
from django.urls import path
from . import views

app_name = 'notification'

urlpatterns = [
    # AJAX API 路由
    path('api/unread/', views.get_unread_notifications, name='api_unread'),
    path('api/mark-all-read/', views.mark_all_read, name='api_mark_all_read'),

    # 消息中转与跳转路由
    path('read/<int:pk>/', views.mark_as_read_and_redirect, name='read_and_redirect'),
]