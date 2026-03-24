# notification/views.py
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.timezone import localtime
from django.urls import reverse
from .models import Notification
from django.shortcuts import render
from django.core.paginator import Paginator
import json


@login_required
def get_unread_notifications(request):
    """
    获取当前用户的未读消息总数及最近的 5 条【未读】消息记录 (AJAX API)
    """
    # 核心修正：只筛选 is_read=False 的消息
    unread_notifications = Notification.objects.filter(recipient=request.user, is_read=False)

    # 计算未读总数
    unread_count = unread_notifications.count()

    # 获取最近的 5 条未读消息
    recent_unread_notifs = unread_notifications.order_by('-created_at')[:5]

    notifications_data = []
    for notif in recent_unread_notifs:
        # 下发中转站 URL
        redirect_url = reverse('notification:read_and_redirect', kwargs={'pk': notif.id})

        notifications_data.append({
            'id': notif.id,
            'title': notif.title,
            'message': getattr(notif, 'message', ''),
            'is_read': notif.is_read,  # 此时这里必然是 False
            'notice_type': getattr(notif, 'notice_type', 'info'),
            'created_at': localtime(notif.created_at).strftime('%Y-%m-%d %H:%M'),
            'url': redirect_url,
        })

    return JsonResponse({
        'unread_count': unread_count,
        'notifications': notifications_data
    })


@login_required
@require_POST
def mark_all_read(request):
    """
    一键清空：将当前用户的所有未读消息标记为已读
    """
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success', 'message': '已全部标为已读'})


@login_required
def mark_as_read_and_redirect(request, pk):
    """
    标记已读并跳转
    """
    # TODO 跳转时保存已读时间，主页上添加已读时间显示。
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)

    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])

    raw_url = getattr(notif, 'target_url', getattr(notif, 'url', '#'))

    # URL 清洗逻辑保持不变
    clean_url = raw_url
    if clean_url != '#':
        if clean_url.startswith('127.0.0.1') or clean_url.startswith('localhost'):
            clean_url = f"http://{clean_url}"
        elif not clean_url.startswith('http') and not clean_url.startswith('/'):
            clean_url = f"/{clean_url}"

    return redirect(clean_url)


@login_required
def notification_index(request):
    """消息主页视图（含分页）"""
    # 获取该用户的所有消息，按时间倒序
    all_notifs = Notification.objects.filter(recipient=request.user).order_by('-created_at')

    paginator = Paginator(all_notifs, 15)  # 每页15条
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'notification/notification_list.html', {
        'notifications': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    })


@login_required
@require_POST
def mark_single_read(request):
    """API: 标记单条消息为已读"""
    data = json.loads(request.body)
    notif_id = data.get('id')
    Notification.objects.filter(id=notif_id, recipient=request.user).update(is_read=True)
    return JsonResponse({'status': 'success'})


@login_required
@require_POST
def delete_notification(request):
    """API: 彻底删除单条消息记录"""
    data = json.loads(request.body)
    notif_id = data.get('id')
    Notification.objects.filter(id=notif_id, recipient=request.user).delete()
    return JsonResponse({'status': 'success'})