from django.views.generic import CreateView, UpdateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.shortcuts import redirect
from django.db import transaction
from django.db.models import Q
from django.contrib import messages
from django.utils import timezone

# === Models & Utils ===
from production.models.cvn_distillation import CVNDistillation
from core.constants import ProcedureState, ProcedureAction, KettleState
from production.models.kettle import Kettle
from production.signals import post_procedure_state_change
from production.utils.batch_generator import generate_batch_number

# 预留引入，后续我们将创建对应的 Form 和 Service
from production.forms.cvn_distillation_form import CVNDistillationForm
from production.services import cvn_distillation_service


# ========================================================
# 1. 开单视图 (Create View)
# ========================================================
class CVNDistillationCreateView(LoginRequiredMixin, CreateView):
    """
    职责：
    1. 选择釜皿、录入多批次粗品来源。
    2. 生成正式批次号 (前缀 CVN-DIS)。
    3. 创建状态为 'new' (新建/待投) 的单据。
    """
    model = CVNDistillation
    template_name = 'production/procedure/cvn_distillation.html'
    form_class = CVNDistillationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['action_type'] = self.request.POST.get('action')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 传递釜皿状态供前端选择器使用
        context['available_kettles'] = Kettle.objects.filter(status=KettleState.IDLE)
        context['cleaning_kettles'] = Kettle.objects.filter(status=KettleState.CLEANING)
        # 注入可用的粗品批次 JSON (供动态明细表使用)
        context['available_sources_json'] = cvn_distillation_service.get_available_synthesis_batches_json()
        return context

    def form_valid(self, form):
        # 生成精馏专用的正式批次号
        batch_no = generate_batch_number(CVNDistillation, 'CVN-DIS')
        form.instance.batch_no = batch_no

        # 强制初始状态为 'new'
        form.instance.status = ProcedureState.NEW

        # 绑定操作员
        form.instance.operator = self.request.user

        response = super().form_valid(form)
        # 新工单入数据库后，发送计划已创建消息
        post_procedure_state_change.send(sender=self.object.__class__, instance=self.object,
                                         old_status='Not_Created', new_status=self.object.status,
                                         user=self.request.user)
        messages.success(self.request, f"精馏工单 {batch_no} 已创建，请确认投入明细无误后点击“确认投产”。")
        return response

    def get_success_url(self):
        return reverse('production:cvn_distillation_update', kwargs={'pk': self.object.pk})


# ========================================================
# 2. 流转与结单视图 (Update View)
# ========================================================
class CVNDistillationUpdateView(LoginRequiredMixin, UpdateView):
    """
    职责：
    1. 状态机引擎：处理 'new' -> 'running' -> 'completed' 的流转。
    2. 事务处理：粗品库存扣减、釜皿状态变更、精品入库。
    """
    model = CVNDistillation
    template_name = 'production/procedure/cvn_distillation.html'
    form_class = CVNDistillationForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['action_type'] = self.request.POST.get('action')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['available_kettles'] = Kettle.objects.filter(status=KettleState.IDLE)
        context['cleaning_kettles'] = Kettle.objects.filter(status=KettleState.CLEANING)
        # 同样注入可用的粗品批次 JSON
        context['available_sources_json'] = cvn_distillation_service.get_available_synthesis_batches_json()
        return context

    def form_valid(self, form):
        action = self.request.POST.get('action')
        current_status = form.instance.status

        try:
            with transaction.atomic():
                # 无条件保存工单页信息
                form.save()

                # 1. 投产 (Start) - 扣减前置粗品库存
                if action == ProcedureAction.START_PRODUCTION and current_status == ProcedureState.NEW:
                    cvn_distillation_service.process_start(form.instance, self.request.user)
                    messages.success(self.request, f"精馏批次 {form.instance.batch_no} 已投产！粗品库存已锁定/扣减。")

                # 2. 完工 (Finish) - 增加精品库存，记录釜残
                elif action == ProcedureAction.FINISH_PRODUCTION and current_status == ProcedureState.RUNNING:
                    cvn_distillation_service.process_finish(form.instance, self.request.user)
                    messages.success(self.request, f"精馏批次 {form.instance.batch_no} 已完工！精品产出已记录，设备已释放。")

                # 3. 统一的数据保存 (涵盖新建时的草稿和生产中的记录更新)
                elif action == ProcedureAction.SAVE_DRAFT:
                    form.save()
                    messages.info(self.request, "工单信息及记录已成功保存。")

                # 4. 异常兜底 (防范前端被篡改传来了莫名其妙的指令)
                else:
                    form.save()  # 依然保存数据防丢失，但给出警告
                    messages.warning(self.request, f"执行了未知的操作指令 '{action}'，数据已默认保存。")

        except Exception as e:
            messages.error(self.request, f"操作失败: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.get_success_url())

    def get_success_url(self):
        return reverse('production:cvn_distillation_update', kwargs={'pk': self.object.pk})


# ========================================================
# 3. 列表视图 (List View)
# ========================================================
class CVNDistillationListView(LoginRequiredMixin, ListView):
    model = CVNDistillation
    template_name = 'production/procedure_list/procedure_list_cvn_distillation.html'
    context_object_name = 'procedures'
    paginate_by = 20
    ordering = ['-start_time', '-id']

    def get_queryset(self):
        qs = super().get_queryset()

        # 1. 状态筛选
        status_filter = self.request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        # 2. 批次号模糊搜索 (对应前端的 q 字段)
        search_query = self.request.GET.get('q')
        if search_query:
            qs = qs.filter(batch_no__icontains=search_query)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 传回前端保持筛选状态
        context['current_status'] = self.request.GET.get('status', '')
        context['search_query'] = self.request.GET.get('q', '')
        context['status_choices'] = ProcedureState.choices
        return context