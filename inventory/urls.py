from django.urls import path
from django_ratelimit.decorators import ratelimit
from inventory.views import InventoryListView, InventoryActionView, InventoryHistoryView

app_name = 'inventory'

# 定义库存核心限流器：防连击并发，限制单个用户每 10 秒只能提交 1 次 POST 请求
anti_double_click = ratelimit(key='user', rate='1/10s', method='POST', block=True)

urlpatterns = [
    # 访问路径: /inventory/ (列表查询，暂不限制 POST，且 GET 不受限)
    path('', InventoryListView.as_view(), name='inventory_list'),

    # 访问路径: /inventory/action/
    # 🔐 核心防线：对库存具体操作加装防连击装配器
    path('action/', anti_double_click(InventoryActionView.as_view()), name='inventory_action'),

    # 访问路径: /inventory/history/ (历史记录查询)
    path('history/', InventoryHistoryView.as_view(), name='inventory_history'),
]