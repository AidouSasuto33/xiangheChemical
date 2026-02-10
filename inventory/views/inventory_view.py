from django.views.generic import ListView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse_lazy
from django.db.models import Q

# 引入你的 models 和 services
from inventory.models import Inventory, InventoryLog
from inventory.services.inventory_service import handle_inventory_action


# ==========================================
# 1. 库存列表视图 (GET)
# ==========================================
class InventoryListView(LoginRequiredMixin, ListView):
    """
    展示实时库存列表
    继承 ListView 后，Django 帮你处理了 get_queryset 和 template 渲染
    """
    model = Inventory
    template_name = 'inventory/inventory_list.html'
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
        支持搜索(q)、分类筛选(cat)、排序(sort)
        """
        qs = super().get_queryset()
        
        # 1. 搜索 (q)
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(key__icontains=q))

        # 2. 分类筛选 (cat)
        category = self.request.GET.get('cat')
        if category:
            qs = qs.filter(category=category)

        # 3. 排序 (sort)
        sort_by = self.request.GET.get('sort')
        if sort_by == 'name':
            qs = qs.order_by('name')
        elif sort_by == 'category':
            qs = qs.order_by('category')
        elif sort_by == 'quantity':
            qs = qs.order_by('quantity')
        elif sort_by == '-quantity':
            qs = qs.order_by('-quantity')
            
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
            messages.success(request, f"{message}")
        else:
            messages.error(request, f"{message}")

        # 4. 重定向回列表页
        # 这里使用 reverse_lazy 或者直接写 url name 都可以，redirect 支持 url name
        return redirect('inventory:inventory_list')


# ==========================================
# 3. 库存历史记录视图 (History)
# ==========================================
class InventoryHistoryView(LoginRequiredMixin, ListView):
    """
    单品库存变动历史
    URL参数: ?id=1 (必填)
    """
    model = InventoryLog
    template_name = 'inventory/inventory_history.html'
    context_object_name = 'logs'
    paginate_by = 20  # 每页20条，防止数据太多卡顿

    def get_queryset(self):
        # 1. 获取当前要查看的 inventory_id
        inventory_id = self.request.GET.get('id')
        if not inventory_id:
            return InventoryLog.objects.none()  # 如果没传ID，啥也不显示

        # 2. 基础查询
        qs = InventoryLog.objects.filter(inventory_id=inventory_id).select_related('operator')

        # 3. 筛选: 操作类型
        action = self.request.GET.get('action')
        if action:
            qs = qs.filter(action_type=action)

        # 4. 筛选: 时间范围 (可选)
        date_start = self.request.GET.get('date_start')
        date_end = self.request.GET.get('date_end')
        if date_start:
            qs = qs.filter(created_at__date__gte=date_start)
        if date_end:
            qs = qs.filter(created_at__date__lte=date_end)
            
        # 5. 搜索备注 (多关键词 AND)
        q = self.request.GET.get('q')
        if q:
            for keyword in q.split():
                qs = qs.filter(note__icontains=keyword)

        # 6. 排序
        sort = self.request.GET.get('sort')
        if sort == 'oldest':
            return qs.order_by('created_at')
        
        # 默认最新的在最上面
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 把当前的 Inventory 对象传给模板，用于显示标题
        inventory_id = self.request.GET.get('id')
        if inventory_id:
            try:
                current_item = Inventory.objects.get(pk=inventory_id)
                context['current_item'] = current_item
                
                # 计算上一条和下一条 (循环逻辑)
                current_id = current_item.id
                
                # 下一条: ID > current_id 的第一条，如果没有则取整个表的第一条
                next_item = Inventory.objects.filter(id__gt=current_id).order_by('id').first()
                if not next_item:
                    next_item = Inventory.objects.order_by('id').first()
                context['next_item'] = next_item
                
                # 上一条: ID < current_id 的最后一条，如果没有则取整个表的最后一条
                prev_item = Inventory.objects.filter(id__lt=current_id).order_by('-id').first()
                if not prev_item:
                    prev_item = Inventory.objects.order_by('-id').first()
                context['prev_item'] = prev_item
                
            except Inventory.DoesNotExist:
                pass
        return context