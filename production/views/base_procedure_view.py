# production/views/base_procedure_view.py

from django.views.generic import CreateView, UpdateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.shortcuts import redirect
from django.db import transaction
from django.contrib import messages

from core.constants import ProcedureState, ProcedureAction
from production.signals import post_procedure_state_change
from production.utils.batch_generator import generate_batch_number


# ========================================================
# 1. 核心混入基类 (Core Mixin)
# ========================================================
class BaseProcedureView:
    """
    生产工艺视图的纯逻辑混入类 (Mixin)。
    提供共享变量声明和通用的上下文、参数及重定向处理。
    注意：此类不直接继承任何 Django 原生 View，以避免 MRO 冲突。
    """
    # 子类必须覆盖的变量
    model = None
    form_class = None
    service_class = None
    template_name = None
    reverse_str = None  # 例如: 'production:cvn_synthesis_update'
    batch_no_prefix = None  # 例如: 'CVN-SYN'

    # 子类可选覆盖的变量
    require_source_batches = False  # 是否需要获取前置批次（精馏等工艺需要改为 True）

    def get_form_kwargs(self):
        """统一提取前端传入的 action_type，供 Form 内部校验使用"""
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['action_type'] = self.request.POST.get('action')
        return kwargs

    def get_context_data(self, **kwargs):
        """统一调用 Service 层获取页面渲染所需的上下文（BOM、釜皿等）"""
        context = super().get_context_data(**kwargs)
        if self.require_source_batches:
            # 获取当前实例（如果是新建页面，self.object 可能为 None）
            current_instance = getattr(self, 'object', None)

            # 核心改动：将 instance 传给 Service
            context['bom_data'] = self.service_class.get_production_context(
                instance=current_instance,
                require_source_batches=self.require_source_batches
            )
        return context

    def get_success_url(self):
        """统一的提交后重定向逻辑：跳转回该单据的 update 页面"""
        if not self.reverse_str:
            raise NotImplementedError("子类必须提供 reverse_str 变量以便重定向。")
        return reverse(self.reverse_str, kwargs={'pk': self.object.pk})


# ========================================================
# 2. 开单视图基类 (Create View Base)
# ========================================================
class BaseProcedureCreateView(LoginRequiredMixin, BaseProcedureView, CreateView):
    """
    通用的工艺开单视图。
    负责：生成批次号、初始化状态、绑定操作员、发送创建信号。
    """

    def form_valid(self, form):
        if not self.batch_no_prefix:
            raise NotImplementedError("CreateView 子类必须提供 batch_no_prefix 以生成批次号。")

        # 1. 生成正式批次号
        batch_no = generate_batch_number(self.model, self.batch_no_prefix)
        form.instance.batch_no = batch_no

        # 2. 强制初始状态为 'new'
        form.instance.status = ProcedureState.NEW

        # 3. 绑定操作员
        form.instance.operator = self.request.user

        # 4. 保存单据
        response = super().form_valid(form)

        # 5. 发送计划已创建消息
        post_procedure_state_change.send(
            sender=self.object.__class__,
            instance=self.object,
            old_status='Not_Created',
            new_status=self.object.status,
            user=self.request.user
        )
        messages.success(self.request, f"生产单 {batch_no} 已创建，请确认无误后点击“确认投产”。")
        return response


# ========================================================
# 3. 流转与结单视图基类 (Update View Base)
# ========================================================
class BaseProcedureUpdateView(LoginRequiredMixin, BaseProcedureView, UpdateView):
    """
    通用的工艺流转视图。
    负责：调度 Service 层处理投产与完工逻辑、执行事务管控与异常拦截。
    """

    def form_valid(self, form):
        action = self.request.POST.get('action')
        current_status = form.instance.status

        if not self.service_class:
            raise NotImplementedError("UpdateView 子类必须提供 service_class 以处理业务逻辑。")

        try:
            with transaction.atomic():
                # 无条件先保存工单页面的基础信息和记录
                form.save()

                # 1. 投产 (Start)
                if action == ProcedureAction.START_PRODUCTION and current_status == ProcedureState.NEW:
                    self.service_class.process_start(form.instance, self.request.user)
                    messages.success(self.request, f"批次 {form.instance.batch_no} 已投产！原料/粗品库存已扣减。")

                # 2. 完工 (Finish)
                elif action == ProcedureAction.FINISH_PRODUCTION and current_status == ProcedureState.RUNNING:
                    self.service_class.process_finish(form.instance, self.request.user)
                    messages.success(self.request, f"批次 {form.instance.batch_no} 已完工！产出已记录，设备已释放。")

                # 3. 统一的数据保存
                elif action == ProcedureAction.SAVE_DRAFT:
                    messages.info(self.request, "工单信息及记录已成功保存。")

                # 4. 异常兜底
                else:
                    messages.warning(self.request, f"执行了未知的操作指令 '{action}'，数据已默认保存。")

        except Exception as e:
            # 捕获服务层抛出的 ValidationError 或 ValueError 并回滚事务
            messages.error(self.request, f"操作失败: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.get_success_url())


# ========================================================
# 4. 列表视图基类 (List View Base)
# ========================================================
class BaseProcedureListView(LoginRequiredMixin, ListView):
    """
    通用的工艺列表视图。
    负责：统一的分页设定、状态与单号筛选器接入。
    """
    context_object_name = 'procedures'
    paginate_by = 9 # TODO 若想设置分页数量大于9，则需要在顶部状态栏同样添加分页。且将分页做成partial html
    ordering = ['-batch_no', '-id']

    def get_queryset(self):
        qs = super().get_queryset()

        # 1. 状态筛选
        status_filter = self.request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        # 2. 批次号模糊搜索
        search_query = self.request.GET.get('q')
        if search_query:
            qs = qs.filter(batch_no__icontains=search_query)

        # 3. 釜皿筛选 (预留可选扩展)
        kettle_filter = self.request.GET.get('kettle_id')
        if kettle_filter:
            qs = qs.filter(kettle_id=kettle_filter)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 传回前端以保持筛选状态和呈现可选项
        context['current_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('q', '')
        context['status_choices'] = ProcedureState.choices

        return context