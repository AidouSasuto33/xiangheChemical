from django.views.generic import CreateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.db import transaction

# 引入相关模型
from production.models.cvn_synthesis import CVNSynthesis
from production.models.kettle import Kettle


class CVNSynthesisCreateView(LoginRequiredMixin, CreateView):
    model = CVNSynthesis
    template_name = 'procedure/cvn_synthesis.html'
    # 定义表单字段 (注意：kettle 字段由前端组件处理，但必须在 fields 里)
    fields = [
        'start_time', 'end_time', 'kettle',
        'raw_dcb', 'raw_nacn', 'raw_tbab', 'raw_alkali',
        'crude_weight', 'remarks'
    ]
    # 成功后跳转回看板 (暂定)
    success_url = reverse_lazy('production:kettle_dashboard')

    def get_context_data(self, **kwargs):
        """
        核心逻辑：筛选适合 CVN 合成工艺的釜皿，并按状态分组
        """
        context = super().get_context_data(**kwargs)

        # 1. 筛选支持 'cvn_syn' 工艺的设备
        # 注意：这里假设 supported_processes 是 JSONField 或 ArrayField
        # 修复：Postgres ArrayField 查询应使用 list 包含字符串
        relevant_kettles = Kettle.objects.filter(supported_processes__contains=['cvn_syn'])

        # 2. 分组传入 Context
        context['available_kettles'] = relevant_kettles.filter(status='idle').order_by('name')
        context['cleaning_kettles'] = relevant_kettles.filter(status='to_clean').order_by('name')

        return context

    def form_valid(self, form):
        """
        表单提交后的处理逻辑
        """
        # 1. 自动绑定操作员
        form.instance.operator = self.request.user

        # 2. 处理“环保/回收”临时字段 (非 Model 字段)
        # 前端虽然有 input，但不在 Model fields 里，需要手动捕获并追加到备注
        recycle_val = self.request.POST.get('recycle_solvent')
        waste_val = self.request.POST.get('waste_water')

        extra_notes = []
        if recycle_val:
            extra_notes.append(f"[环保] 回收溶剂: {recycle_val}kg")
        if waste_val:
            extra_notes.append(f"[环保] 废水排出: {waste_val}kg")

        if extra_notes:
            original_remarks = form.instance.remarks or ""
            # 追加到现有备注后
            form.instance.remarks = f"{original_remarks}\n" + " | ".join(extra_notes)

        # 3. 事务保存 (为了后续可能扩展的库存扣减逻辑)
        with transaction.atomic():
            response = super().form_valid(form)
            # 这里未来可以插入：InventoryLog.objects.create(...)

            # 4. 连带更新釜皿状态 (关键！)
            # 选中了某个釜，状态应变为 Running，写入批号
            kettle = form.instance.kettle
            kettle.status = 'running'
            kettle.current_batch_no = form.instance.batch_no
            kettle.last_process = 'cvn_syn'
            # 简单估算：当前投入量 = 原料总和
            total_input = (form.instance.raw_dcb + form.instance.raw_nacn +
                           form.instance.raw_tbab + form.instance.raw_alkali)
            kettle.current_level = total_input
            kettle.save()

            return response