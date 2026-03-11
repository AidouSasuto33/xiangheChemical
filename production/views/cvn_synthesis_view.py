from django.views.generic import CreateView, UpdateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse
from django.shortcuts import redirect
from django.db import transaction
from django.contrib import messages
# === Models & Utils ===
from core.constants import ProcedureState, ProcedureAction, KettleState
from production.models.cvn_synthesis import CVNSynthesis
from production.models.kettle import Kettle
from production.signals import post_procedure_state_change
from production.utils.batch_generator import generate_batch_number
from production.services import cvn_synthesis_service
from production.forms.cvn_synthesis_form import CVNSynthesisForm


# ========================================================
# 1. 开单视图 (Create View)
# ========================================================
class CVNSynthesisCreateView(LoginRequiredMixin, CreateView):
    """
    职责：
    1. 选择釜皿、录入原料配方、预计开工时间。
    2. 生成正式批次号。
    3. 创建状态为 'new' (新建/待投) 的单据。
    注意：此阶段不扣库存，不锁死釜皿（仅逻辑占用）。
    """
    model = CVNSynthesis
    template_name = 'production/procedure/cvn_synthesis.html'
    form_class = CVNSynthesisForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['action_type'] = self.request.POST.get('action')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Populate kettle lists for the selector
        context['available_kettles'] = Kettle.objects.filter(status=KettleState.IDLE)
        context['cleaning_kettles'] = Kettle.objects.filter(status=KettleState.CLEANING)
        return context

    def form_valid(self, form):
        # 1. 生成正式批次号 (仅在保存瞬间生成)
        batch_no = generate_batch_number(CVNSynthesis, 'CVN-SYN')
        form.instance.batch_no = batch_no

        # 2. 强制初始状态为 'new'
        form.instance.status = ProcedureState.NEW

        # 3. 绑定操作员
        form.instance.operator = self.request.user

        # 4. 保存单据
        response = super().form_valid(form)
        # 新工单入数据库后，发送计划已创建消息
        post_procedure_state_change.send(sender=self.object.__class__, instance=self.object,
                                         old_status='Not_Create', new_status=self.object.status,
                                         user=self.request.user)
        messages.success(self.request, f"生产单 {batch_no} 已创建，请确认无误后点击“确认投产”。")
        return response

    def get_success_url(self):
        # 创建成功后，跳转到该单据的“编辑/流转”页面
        # 假设 URL 命名为 'cvn_synthesis_update'
        return reverse('production:cvn_synthesis_update', kwargs={'pk': self.object.pk})


# ========================================================
# 2. 流转与结单视图 (Update View)
# ========================================================
class CVNSynthesisUpdateView(LoginRequiredMixin, UpdateView):
    """
    职责：
    1. 状态机引擎：处理 'new' -> 'running' -> 'completed' 的流转。
    2. 事务处理：库存扣减、釜皿状态变更。
    3. 数据补录：完工时录入产出。
    """
    model = CVNSynthesis
    template_name = 'production/procedure/cvn_synthesis.html'
    form_class = CVNSynthesisForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        if self.request.method in ('POST', 'PUT'):
            kwargs['action_type'] = self.request.POST.get('action')
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Populate kettle lists for the selector
        context['available_kettles'] = Kettle.objects.filter(status=KettleState.IDLE)
        context['cleaning_kettles'] = Kettle.objects.filter(status=KettleState.CLEANING)
        return context

    def form_valid(self, form):
        action = self.request.POST.get('action')  # 获取按钮动作
        current_status = form.instance.status

        try:
            with transaction.atomic():
                # 无条件保存工单页信息
                form.save()

                # 1. 投产 (Start)
                if action == ProcedureAction.START_PRODUCTION and current_status == ProcedureState.NEW:
                    cvn_synthesis_service.process_start(form.instance, self.request.user)
                    messages.success(self.request, f"批次 {form.instance.batch_no} 已投产！原料库存已扣减。")

                # 2. 完工 (Finish)
                elif action == ProcedureAction.FINISH_PRODUCTION and current_status == ProcedureState.RUNNING:
                    cvn_synthesis_service.process_finish(form.instance, self.request.user)
                    messages.success(self.request, f"批次 {form.instance.batch_no} 已完工！产出已入库，设备已释放。")

                # 3. 统一的数据保存 (涵盖新建时的草稿和生产中的记录更新)
                elif action == ProcedureAction.SAVE_DRAFT:
                    form.save()
                    messages.info(self.request, "工单信息及记录已成功保存。")

                # 4. 异常兜底 (防范前端被篡改传来了莫名其妙的指令)
                else:
                    form.save()  # 依然保存数据防丢失，但给出警告
                    messages.warning(self.request, f"执行了未知的操作指令 '{action}'，数据已默认保存。")

        except Exception as e:
            # 捕获库存不足等异常，回滚事务
            messages.error(self.request, f"操作失败: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.get_success_url())

    def get_success_url(self):
        # 操作完停留在当前页面，或者跳转回看板（视需求而定）
        return reverse('production:cvn_synthesis_update', kwargs={'pk': self.object.pk})


# ========================================================
# 3. 列表视图 (List View)
# ========================================================
class CVNSynthesisListView(LoginRequiredMixin, ListView):
    model = CVNSynthesis
    template_name = 'production/procedure_list/procedure_list_cvn_synthesis.html'
    context_object_name = 'procedures'
    paginate_by = 20
    ordering = ['-start_time', '-id']  # 默认按时间倒序

    def get_queryset(self):
        qs = super().get_queryset()

        # === 筛选逻辑 ===
        # 1. 状态筛选
        status_filter = self.request.GET.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        # 2. 釜皿筛选 (可选增强)
        kettle_filter = self.request.GET.get('kettle_id')
        if kettle_filter:
            qs = qs.filter(kettle_id=kettle_filter)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 传入当前筛选状态，用于回显 Filter 栏
        context['current_status'] = self.request.GET.get('status', '')
        context['status_choices'] = ProcedureState.choices
        return context