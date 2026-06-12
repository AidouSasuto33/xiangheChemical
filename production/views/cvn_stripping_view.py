# production/views/cvn_stripping_view.py
from production.forms.cvn_stripping_form import CVNStrippingForm
from production.models.cvn_stripping import CVNStripping
from production.services.cvn_stripping_service import CVNStrippingService
from production.views.base_procedure_view import (
    BaseProcedureView,
    BaseProcedureListView,
    BaseProcedureCreateView,
    BaseProcedureUpdateView
)


class CVNStrippingBaseView(BaseProcedureView):
    # 核心模型、Form与Service层绑定
    model = CVNStripping
    form_class = CVNStrippingForm
    service_class = CVNStrippingService

    # 路由与模板映射
    template_name = 'production/procedure/cvn_stripping.html'
    reverse_str = 'production:cvn_stripping_update'

    # 批次号前缀规范
    batch_no_prefix = 'CVN-STR'

    # 明确粗蒸需要获取前置合成液批次
    require_source_batches = True


class CVNStrippingCreateView(CVNStrippingBaseView, BaseProcedureCreateView):
    pass


class CVNStrippingUpdateView(CVNStrippingBaseView, BaseProcedureUpdateView):
    pass


class CVNStrippingListView(CVNStrippingBaseView, BaseProcedureListView):
    template_name = 'production/procedure_list/procedure_list_cvn_stripping.html'

    def get_queryset(self):
        # 预加载子表领料数据及其对应的来源批次，防止列表页出现 N+1 SQL 查询异常
        return super().get_queryset().prefetch_related('inputs__source_batch')