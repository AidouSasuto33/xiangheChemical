from django.urls import path
from inventory.views import InventoryListView, InventoryActionView, InventoryHistoryView

app_name = 'inventory'

urlpatterns = [
    # 访问路径: /inventory/
    path('', InventoryListView.as_view(), name='inventory_list'),
    
    # 访问路径: /inventory/action/
    path('action/', InventoryActionView.as_view(), name='inventory_action'),
    
    # 访问路径: /inventory/history/
    path('history/', InventoryHistoryView.as_view(), name='inventory_history'),
]