# notification/views.py
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.utils.timezone import localtime
from .models import Notification


@login_required
def get_unread_notifications(request):
    """
    获取当前用户的未读消息总数及最近的 5 条消息记录 (AJAX API)
    """
    # 获取属于当前用户的通知
    # 关联用户的外键叫 'recipient', 所以recipient=
    user_notifications = Notification.objects.filter(recipient=request.user)

    # 计算未读总数
    unread_count = user_notifications.filter(is_read=False).count()

    # 获取最近的5条（包含已读和未读，用于在下拉菜单中展示）
    recent_notifs = user_notifications.order_by('-created_at')[:5]

    notifications_data = []
    for notif in recent_notifs:
        # 获取原始 URL
        raw_url = getattr(notif, 'target_url', getattr(notif, 'url', '#'))

        # URL 清洗逻辑：防止前端相对路径拼接
        clean_url = raw_url
        if clean_url != '#':
            # 如果数据库存了域名但没加 http://，自动补全
            if clean_url.startswith('127.0.0.1') or clean_url.startswith('localhost'):
                clean_url = f"http://{clean_url}"
            # 如果既不是完整网址，也不是以 '/' 开头的绝对路径，加 '/'
            elif not clean_url.startswith('http') and not clean_url.startswith('/'):
                clean_url = f"/{clean_url}"
        notifications_data.append({
            'id': notif.id,
            'title': notif.title,
            # 防御性获取：如果你没有 message 字段，返回空字符串
            'message': getattr(notif, 'message', ''),
            'is_read': notif.is_read,
            # 防御性获取：默认为 info 类型
            'notice_type': getattr(notif, 'notice_type', 'info'),
            # 格式化时间，去掉秒，更符合阅读习惯
            'created_at': localtime(notif.created_at).strftime('%Y-%m-%d %H:%M'),
            # 防御性获取：假设你的跳转链接字段叫 target_url 或 url
            'url': clean_url,
        })

    return JsonResponse({
        'unread_count': unread_count,
        'notifications': notifications_data
    })


@login_required
@require_POST
def mark_all_read(request):
    """
    将当前用户的所有未读消息一键标记为已读 (AJAX API)
    """
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'success', 'message': '已全部标为已读'})