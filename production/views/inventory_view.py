from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy

# 引入你的 models 和 services
from ..models.inventory import Inventory
from ..services.inventory_service import handle_inventory_action


# ==========================================
# 1. 库存列表视图 (GET)
# ==========================================
class InventoryListView(LoginRequiredMixin, ListView):
    """
    展示实时库存列表
    继承 ListView 后，Django 帮你处理了 get_queryset 和 template 渲染
    """
    model = Inventory
    template_name = 'production/inventory_list.html'
    context_object_name = 'inventory_items'  # 模板里使用的变量名

    # 默认排序
    ordering = ['category', 'key']

    def get_context_data(self, **kwargs):
        """
        如果你想传额外的上下文（比如页面标题），重写这个方法
        """
        context = super().get_context_data(**kwargs)
        context['page_title'] = '实时库存总览'
        return context

    def get_queryset(self):
        """
        将来你要做'复杂排序'或'筛选'时，就在这里改代码。
        例如：只看原材料 -> self.request.GET.get('cat')
        """
        qs = super().get_queryset()
        # 可以在这里加逻辑，比如:
        # category = self.request.GET.get('category')
        # if category:
        #     qs = qs.filter(category=category)
        return qs


# ==========================================
# 2. 库存操作视图 (POST)
# ==========================================
class InventoryActionView(LoginRequiredMixin, View):
    """
    处理购入、销售、盘点 (纯后端接口，处理完重定向)
    """

    def post(self, request, *args, **kwargs):
        # 1. 提取参数
        inventory_id = request.POST.get('inventory_id')
        action_type = request.POST.get('action_type')
        amount = request.POST.get('amount')
        note = request.POST.get('note', '')

        # 2. 调用 Service (逻辑层)
        # 注意：这里传 request.user，而不是 request.request.user
        success, message = handle_inventory_action(
            user=request.user,
            inventory_id=inventory_id,
            action_type=action_type,
            amount_or_quantity=amount,
            note=note
        )

        # 3. 反馈消息
        if success:
            messages.success(request, f"✅ {message}")
        else:
            messages.error(request, f"❌ {message}")

        # 4. 重定向回列表页
        # 这里使用 reverse_lazy 或者直接写 url name 都可以，redirect 支持 url name
        return redirect('inventory_list')