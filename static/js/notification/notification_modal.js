// static/js/notification/notification_modal.js

document.addEventListener('DOMContentLoaded', function() {
    // --- 配置项 ---
    const POLLING_INTERVAL = 30000; // 轮询间隔：30秒 (30000毫秒)

    // API 路由约定：接下来的后端开发中我们会实现这两个接口
    const API_GET_NOTIFICATIONS = 'http://127.0.0.1:8000/notification/api/unread/'; //TODO 服务器上线后改为正式域名
    const API_MARK_ALL_READ = '/notification/api/mark-all-read/';

    // --- DOM 元素引用 ---
    const badge = document.getElementById('notification-badge');
    const countText = document.getElementById('unread-count-text');
    const listContainer = document.getElementById('notification-list-container');
    const emptyState = document.getElementById('notification-empty-state');
    const markAllReadBtn = document.getElementById('mark-all-read-btn');
    const toastContainer = document.getElementById('toast-container');

    // 使用 Set 记录已经弹窗提醒过的消息 ID，防止轮询时重复弹窗
    let knownNotificationIds = new Set();

    // --- 核心功能 ---

    // 1. 获取最新通知数据
    async function fetchNotifications() {
        try {
            const response = await fetch(API_GET_NOTIFICATIONS, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json'
                }
            });

            if (!response.ok) throw new Error('网络请求失败');

            const data = await response.json();
            updateUI(data);
            checkForNewNotifications(data.notifications);

        } catch (error) {
            console.error('获取消息通知失败:', error);
        }
    }

    // 2. 更新界面 UI (小红点数字和下拉列表)
    function updateUI(data) {
        const unreadCount = data.unread_count || 0;
        const notifications = data.notifications || [];

        // 更新 Badge 和 Header 数量
        countText.textContent = unreadCount;
        if (unreadCount > 0) {
            badge.textContent = unreadCount > 99 ? '99+' : unreadCount;
            badge.style.display = 'block';
        } else {
            badge.style.display = 'none';
        }

        // 更新下拉面板中的消息列表
        if (notifications.length === 0) {
            listContainer.innerHTML = '';
            if(emptyState) listContainer.appendChild(emptyState);
        } else {
            listContainer.innerHTML = notifications.map(renderNotificationItem).join('');
        }
    }

    // 3. 渲染单条消息的 HTML 结构
    function renderNotificationItem(notif) {
        // 根据是否已读应用不同的背景色和字体加粗样式
        const readClass = notif.is_read ? 'text-muted' : 'fw-bold text-dark bg-light';
        // 根据消息类型配置图标
        const icon = notif.notice_type === 'warning' ? 'bi-exclamation-circle text-warning' : 'bi-bell text-primary';

        return `
            <a href="${notif.url || '#'}" class="dropdown-item border-bottom py-2 ${readClass}" style="white-space: normal;">
                <div class="d-flex align-items-start">
                    <i class="bi ${icon} fs-5 me-2 mt-1"></i>
                    <div>
                        <div class="mb-1">${notif.title}</div>
                        <div class="text-muted" style="font-size: 0.75rem;">
                            ${notif.created_at}
                        </div>
                    </div>
                </div>
            </a>
        `;
    }

    // 4. 检查并触发新消息弹窗 (Toast)
    function checkForNewNotifications(notifications) {
        notifications.forEach(notif => {
            if (!notif.is_read && !knownNotificationIds.has(notif.id)) {
                // 发现全新的未读消息，加入集合并触发右下角弹窗
                knownNotificationIds.add(notif.id);
                showToast(notif);
            }
        });
    }

    // 5. 显示 Bootstrap Toast 弹窗
    function showToast(notif) {
        const toastId = 'toast-' + notif.id;
        const toastHtml = `
            <div id="${toastId}" class="toast align-items-center text-bg-primary border-0 mb-2 shadow" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                    <div class="toast-body">
                        <strong>${notif.title}</strong><br>
                        <small>${notif.message ? notif.message.substring(0, 30) + '...' : '您有一条新消息'}</small>
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="关闭"></button>
                </div>
            </div>
        `;

        toastContainer.insertAdjacentHTML('beforeend', toastHtml);

        const toastElement = document.getElementById(toastId);
        // 初始化并显示 Toast，设定 5 秒后自动消失
        const bsToast = new bootstrap.Toast(toastElement, { delay: 5000 });
        bsToast.show();

        // 弹窗隐藏后将其从 DOM 中移除，避免积累过多无用节点
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }

    // 6. 全部标为已读的 POST 请求
    async function markAllAsRead() {
        try {
            const csrfToken = getCookie('csrftoken');

            const response = await fetch(API_MARK_ALL_READ, {
                method: 'POST',
                headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'X-CSRFToken': csrfToken,
                    'Content-Type': 'application/json'
                }
            });

            if (response.ok) {
                // 标记成功后，立即刷新前端列表和数字
                fetchNotifications();
            }
        } catch (error) {
            console.error('标记已读失败:', error);
        }
    }

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

    // --- 事件监听与初始化 ---

    // 绑定“全部标为已读”按钮事件
    if (markAllReadBtn) {
        markAllReadBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation(); // 防止点击按钮时自动关闭下拉菜单
            markAllAsRead();
        });
    }

    // 页面加载完成后立即拉取一次数据
    fetchNotifications();

    // 启动定时轮询
    setInterval(fetchNotifications, POLLING_INTERVAL);
});