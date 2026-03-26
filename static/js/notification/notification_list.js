// static/js/notification/notification_list.js

document.addEventListener('DOMContentLoaded', function() {
    const listContainer = document.getElementById('main-notification-list');
    const markAllBtn = document.getElementById('page-mark-all-read-btn');

    // 辅助函数：从 Cookie 中获取 Django CSRF Token
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrfToken = getCookie('csrftoken');

    // 1. 全部标为已读
    if (markAllBtn) {
        markAllBtn.addEventListener('click', async function() {
            try {
                // 复用我们上午写好的 mark-all-read 接口
                const response = await fetch('/notification/api/mark-all-read/', {
                    method: 'POST',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken,
                        'Content-Type': 'application/json'
                    }
                });

                if (response.ok) {
                    // 对于主页的“全部标为已读”，最稳妥且视觉最统一的做法是直接刷新页面
                    window.location.reload();
                }
            } catch (error) {
                console.error('标记全部已读失败:', error);
            }
        });
    }

    // 2. 事件委托：处理列表内的单条“已读”和“删除”点击
    if (listContainer) {
        listContainer.addEventListener('click', async function(e) {

            // --- 拦截删除按钮点击 ---
            const deleteBtn = e.target.closest('.btn-delete-notif');
            if (deleteBtn) {
                e.preventDefault();
                e.stopPropagation(); // 阻止事件冒泡触发外层 div 的跳转重定向

                const notifId = deleteBtn.getAttribute('data-id');
                if (confirm('确定要彻底删除这条消息记录吗？')) {
                    deleteNotification(notifId, deleteBtn);
                }
                return;
            }

            // --- 拦截单条标记已读按钮点击 ---
            const readBtn = e.target.closest('.btn-mark-read');
            if (readBtn) {
                e.preventDefault();
                e.stopPropagation(); // 阻止事件冒泡触发外层 div 的跳转

                const notifId = readBtn.getAttribute('data-id');
                markSingleAsRead(notifId, readBtn);
                return;
            }
        });
    }

    // API 调用：标记单条为已读
    async function markSingleAsRead(id, btnElement) {
        try {
            // API 约定: 我们稍后会在 views.py 中实现这个接口
            const response = await fetch('/notification/api/read-single/', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ id: id })
            });

            if (response.ok) {
                // UI 降级操作：去掉未读的高亮样式，变为普通的已读样式
                const item = document.getElementById(`notif-item-${id}`);
                if (item) {
                    item.classList.remove('border-primary', 'bg-light');
                    item.classList.add('border-transparent');

                    const title = item.querySelector('h6');
                    if (title) {
                        title.classList.remove('fw-bold', 'text-dark');
                        title.classList.add('text-muted');
                        // 移除 New 小红点徽章
                        const badge = title.querySelector('.badge');
                        if (badge) badge.remove();
                    }

                    // 隐藏这个已读按钮，保持 UI 清爽
                    btnElement.remove();
                }
            }
        } catch (error) {
            console.error('标记单条已读失败:', error);
        }
    }

    // API 调用：删除单条消息
    async function deleteNotification(id, btnElement) {
        try {
            // API 约定: 我们稍后会在 views.py 中实现这个接口
            const response = await fetch('/notification/api/delete/', {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ id: id })
            });

            if (response.ok) {
                const item = document.getElementById(`notif-item-${id}`);
                if (item) {
                    // 加入一个简易的透明度过渡效果，符合现代交互直觉
                    item.style.transition = 'opacity 0.3s ease';
                    item.style.opacity = '0';
                    setTimeout(() => {
                        item.remove();
                        checkEmptyState();
                    }, 300);
                }
            }
        } catch (error) {
            console.error('删除消息失败:', error);
        }
    }

    // 辅助操作：检查删除后列表是否空了
    function checkEmptyState() {
        const remainingItems = listContainer.querySelectorAll('.list-group-item');
        if (remainingItems.length === 0) {
            // 直接刷新页面，让后端的 Django 模板去渲染那个巨大的空邮箱占位图
            window.location.reload();
        }
    }
});