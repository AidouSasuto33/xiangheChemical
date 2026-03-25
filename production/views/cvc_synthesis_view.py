# production/views/cvc_synthesis_view.py
from production.forms import CVCSynthesisForm
from production.models.cvc_synthesis import CVCSynthesis
from production.services.cvc_synthesis_service import CVCSynthesisService
from production.views.base_procedure_view import BaseProcedureView, BaseProcedureListView, BaseProcedureCreateView, \
    BaseProcedureUpdateView


class CVCSynthesisBaseView(BaseProcedureView):
    # 子类必须覆盖的变量
    model = CVCSynthesis
    form_class = CVCSynthesisForm
    service_class = CVCSynthesisService
    template_name = 'production/procedure/cvc_synthesis.html'
    reverse_str = 'production:cvc_synthesis_update'
    batch_no_prefix = 'CVC-SYN'

    # 子类可选覆盖的变量
    require_source_batches = True  # CVC合成需要前置CVA批次


class CVCSynthesisCreateView(CVCSynthesisBaseView, BaseProcedureCreateView):
    pass


class CVCSynthesisUpdateView(CVCSynthesisBaseView, BaseProcedureUpdateView):
    pass


class CVCSynthesisListView(CVCSynthesisBaseView, BaseProcedureListView):
    template_name = 'production/procedure_list/procedure_list_cvc_synthesis.html'

    def get_queryset(self):
        # 预加载 inputs 及其关联的 source_batch，确保模板能读到数据且不影响查询性能
        return super().get_queryset().prefetch_related('inputs__source_batch')