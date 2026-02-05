from django.views.generic import CreateView, UpdateView, ListView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.shortcuts import redirect
from django.db import transaction
from django.contrib import messages
from django.utils import timezone

# === Models & Utils ===
from production.models.cvn_synthesis import CVNSynthesis
from production.models.kettle import Kettle
from production.models.audit import InventoryLog
from production.models.core import BaseProductionStep
from production.utils.batch_generator import generate_batch_number
from production import constants
from production.services import cvn_synthesis_service


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
    template_name = 'procedure/cvn_synthesis.html'
    fields = [
        'start_time', 'end_time', 'kettle',
        'raw_dcb', 'input_recycled_dcb', 'raw_nacn', 'raw_tbab', 'raw_alkali',
        'remarks'  # 产出字段在新建时不可填
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 筛选可用釜皿：支持 'cvn_syn' 工艺 且 状态为空闲
        # 注意：实际生产中可能需要过滤掉已经被其他 'new' 状态单据占用的釜皿
        relevant_kettles = Kettle.objects.filter(supported_processes__contains=['cvn_syn'])
        context['available_kettles'] = relevant_kettles.filter(status='idle').order_by('name')
        context['cleaning_kettles'] = relevant_kettles.filter(status='to_clean').order_by('name')
        return context

    def form_valid(self, form):
        # 1. 生成正式批次号 (仅在保存瞬间生成)
        batch_no = generate_batch_number(CVNSynthesis, 'CVN-CU')
        form.instance.batch_no = batch_no

        # 2. 强制初始状态为 'new'
        form.instance.status = BaseProductionStep.STATUS_NEW

        # 3. 绑定操作员
        form.instance.operator = self.request.user

        # 4. 保存单据
        response = super().form_valid(form)

        messages.success(self.request, f"生产单 {batch_no} 已创建，请确认无误后点击“确认投产”。")
        return response

    def get_success_url(self):
        # 创建成功后，跳转到该单据的“编辑/流转”页面
        # 假设 URL 命名为 'cvn_synthesis_update'
        return reverse('cvn_synthesis_update', kwargs={'pk': self.object.pk})


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
    template_name = 'procedure/cvn_synthesis.html'
    # 允许编辑所有字段，但前端会根据 status 锁定部分输入框
    fields = [
        'start_time', 'end_time', 'kettle',
        'raw_dcb', 'input_recycled_dcb', 'raw_nacn', 'raw_tbab', 'raw_alkali',
        'crude_weight', 'remarks',
        # 新增字段
        'test_time', 'content_cvn', 'content_dcb', 'content_adn',
        'recovered_dcb_amount', 'waste_batches'
    ]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # 编辑页通常不需要重新选釜，但也传入列表以供显示（前端会锁定）
        relevant_kettles = Kettle.objects.filter(supported_processes__contains=['cvn_syn'])
        context['available_kettles'] = relevant_kettles.filter(status='idle')
        context['cleaning_kettles'] = relevant_kettles.filter(status='to_clean')
        return context

    def form_valid(self, form):
        action = self.request.POST.get('action')  # 获取按钮动作
        current_status = form.instance.status

        try:
            with transaction.atomic():

                # 1. 投产 (Start)
                if action == 'start_production' and current_status == BaseProductionStep.STATUS_NEW:
                    self._handle_start_production(form)
                    messages.success(self.request, f"批次 {form.instance.batch_no} 已投产！原料库存已扣减。")

                # 2. 完工 (Finish)
                elif action == 'finish_production' and current_status == BaseProductionStep.STATUS_RUNNING:
                    self._handle_finish_production(form)
                    messages.success(self.request, f"批次 {form.instance.batch_no} 已完工！产出已入库，设备已释放。")

                # 3. 保存草稿 (New 状态下的保存)
                elif action == 'save_draft':
                    form.save()
                    messages.info(self.request, "草稿已保存，您可以稍后继续编辑或投产。")

                # 4. 保存记录 (Running 状态下的保存)
                elif action == 'save_notes':
                    form.save()
                    messages.info(self.request, "生产记录（备注/工时）已更新。")

                # 5. 兜底 (其他情况)
                else:
                    form.save()
                    messages.info(self.request, "修改已保存。")

        except Exception as e:
            # 捕获库存不足等异常，回滚事务
            messages.error(self.request, f"操作失败: {str(e)}")
            return self.form_invalid(form)

        return redirect(self.get_success_url())

    def get_success_url(self):
        # 操作完停留在当前页面，或者跳转回看板（视需求而定）
        return reverse('cvn_synthesis_update', kwargs={'pk': self.object.pk})

    # -------------------------------------------------------------------------
    # 内部逻辑方法
    # -------------------------------------------------------------------------

    def _handle_start_production(self, form):
        """处理投产逻辑：锁釜、扣料、变状态"""
        instance = form.instance

        # 1. 锁定釜皿
        kettle = instance.kettle
        if kettle.status != 'idle' and kettle.current_batch_no != instance.batch_no:
            raise ValueError(f"设备 {kettle.name} 当前非空闲，无法投产！")

        kettle.status = 'running'
        kettle.current_batch_no = instance.batch_no
        kettle.last_process = 'cvn_syn'
        # 估算当前液位 = 所有原料之和
        total_input = (instance.raw_dcb + instance.raw_nacn + instance.raw_tbab + instance.raw_alkali)
        kettle.current_level = total_input
        kettle.save()

        # 2. 扣减原料库存 (Inventory Deduction) - 使用 Service
        cvn_synthesis_service.process_start(instance, self.request.user)

        # 3. 更新单据状态
        instance.status = BaseProductionStep.STATUS_RUNNING
        form.save()

    def _handle_finish_production(self, form):
        """处理完工逻辑：释釜、入库、归档"""
        instance = form.instance

        # 1. 校验产出
        if (instance.crude_weight or 0) <= 0:
            raise ValueError("完工必须填写有效的产出重量！")

        if not instance.end_time:
            instance.end_time = timezone.now()

        # 2. 释放釜皿
        kettle = instance.kettle
        kettle.status = 'to_clean'  # 转入待清洗
        kettle.current_batch_no = None  # 清空占用
        kettle.current_level = 0
        kettle.last_product_name = "CVN粗品"
        kettle.save()

        # 3. 增加成品库存 (Inventory Addition) - 使用 Service
        cvn_synthesis_service.process_finish(instance, self.request.user)

        # 4. 更新单据状态
        instance.status = BaseProductionStep.STATUS_COMPLETED
        form.save()


# ========================================================
# 3. 列表视图 (List View)
# ========================================================
class CVNSynthesisListView(LoginRequiredMixin, ListView):
    model = CVNSynthesis
    template_name = 'procedure_list/procedure_list_cvn_synthesis.html'
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
        context['status_choices'] = BaseProductionStep.STATUS_CHOICES
        return context