from django.contrib import admin
from django.urls import path, include
# 引入 production 的 views
from production.views import InventoryListView, InventoryActionView, InventoryHistoryView, KettleDashboardView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),

    # 首页 -> 库存列表
    path('', InventoryListView.as_view(), name='index'),

    #########
    # 库存相关URL
    #########
    path('inventory/', InventoryListView.as_view(), name='inventory_list'),
    # 库存操作 (POST 接口)
    path('inventory/action/', InventoryActionView.as_view(), name='inventory_action'),
    # 历史记录
    path('inventory/history/', InventoryHistoryView.as_view(), name='inventory_history'),

    #########
    # 釜皿看板相关URL
    #########
    path('production/dashboard/kettle/', KettleDashboardView.as_view(), name='kettle_dashboard'),
]