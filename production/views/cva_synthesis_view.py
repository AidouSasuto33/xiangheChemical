# production/views/cva_synthesis_view.py
from production.forms import CVASynthesisForm
from production.models.cva_synthesis import CVASynthesis
from production.services.cva_synthesis_service import CVASynthesisService
from production.views.base_procedure_view import BaseProcedureView, BaseProcedureListView, BaseProcedureCreateView, \
    BaseProcedureUpdateView


class CVASynthesisBaseView(BaseProcedureView):
    # 子类必须覆盖的变量
    model = CVASynthesis
    form_class = CVASynthesisForm
    service_class = CVASynthesisService
    template_name = 'production/procedure/cva_synthesis.html'
    reverse_str = 'production:cva_synthesis_update'
    batch_no_prefix = 'CVA-SYN'

    # 子类可选覆盖的变量
    require_source_batches = True  # CVA合成需要前置CVN精品批次


class CVASynthesisCreateView(CVASynthesisBaseView, BaseProcedureCreateView):
    pass


class CVASynthesisUpdateView(CVASynthesisBaseView, BaseProcedureUpdateView):
    pass


class CVASynthesisListView(CVASynthesisBaseView, BaseProcedureListView):
    template_name = 'production/procedure_list/procedure_list_cva_synthesis.html'

    def get_queryset(self):
        # 预加载 inputs 及其关联的 source_batch，确保模板能读到数据且不影响查询性能
        return super().get_queryset().prefetch_related('inputs__source_batch')