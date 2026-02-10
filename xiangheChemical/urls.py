from django.contrib import admin
from django.urls import path, include
from inventory.views import InventoryListView  # 仅首页使用

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),

    # === 首页 (Home) ===
    # 保持原状，直接渲染库存列表 View
    path('', InventoryListView.as_view(), name='index'),

    # === 子应用路由分发 ===
    
    # 库存业务 -> 指向 inventory/urls.py
    # 访问: /inventory/, /inventory/action/
    path('inventory/', include('inventory.urls')),

    # 生产业务 -> 指向 production/urls.py
    path('production/', include('production.urls')),
]