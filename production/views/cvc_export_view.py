# production/views/cvc_export_view.py
from production.forms import CVCExportForm
from production.models.cvc_export import CVCExport
from production.services.cvc_export_service import CVCExportService
from production.views.base_procedure_view import BaseProcedureView, BaseProcedureListView, BaseProcedureCreateView, \
    BaseProcedureUpdateView


class CVCExportBaseView(BaseProcedureView):
    # 子类必须覆盖的变量
    model = CVCExport
    form_class = CVCExportForm
    service_class = CVCExportService
    template_name = 'production/procedure/cvc_export.html'
    reverse_str = 'production:cvc_export_update'
    batch_no_prefix = 'CVC-EXP'

    # 子类可选覆盖的变量
    require_source_batches = True  # 外销精制需要前置 CVC 合成批次


class CVCExportCreateView(CVCExportBaseView, BaseProcedureCreateView):
    pass


class CVCExportUpdateView(CVCExportBaseView, BaseProcedureUpdateView):
    pass


class CVCExportListView(CVCExportBaseView, BaseProcedureListView):
    template_name = 'production/procedure_list/procedure_list_cvc_export.html'

    def get_queryset(self):
        # 预加载 inputs 及其关联的 source_batch，确保模板能读到数据且不影响查询性能
        return super().get_queryset().prefetch_related('inputs__source_batch')