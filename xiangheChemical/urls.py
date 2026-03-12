from django.contrib import admin
from django.urls import path, include
from inventory.views import InventoryListView  # 仅首页使用
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),

    # === 认证与系统 (Auth & System) ===
    # 1. 先加载我们自定义的带限流的登录路由（会被优先命中）
    path('accounts/', include('system.urls')),
    # 2. 兜底加载 Django 默认的认证路由（为 logout, password_change 等功能提供支持）
    path('accounts/', include('django.contrib.auth.urls')),

    # === 首页 (Home) ===
    # 保持原状，直接渲染库存列表 View
    path('', InventoryListView.as_view(), name='index'),

    # === 子应用路由分发 ===

    # 库存业务
    path('inventory/', include('inventory.urls')),

    # 生产业务
    path('production/', include('production.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)