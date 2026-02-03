from django.contrib import admin
from django.urls import path, include
# 引入 production 的 views
from production.views import InventoryListView, InventoryActionView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),

    # 首页 -> 库存列表
    path('', InventoryListView.as_view(), name='index'),

    # 库存列表
    path('inventory/', InventoryListView.as_view(), name='inventory_list'),

    # 库存操作 (POST 接口)
    path('inventory/action/', InventoryActionView.as_view(), name='inventory_action'),
]