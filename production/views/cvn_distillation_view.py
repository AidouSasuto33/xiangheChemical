from production.forms import CVNDistillationForm
from production.models.cvn_distillation import CVNDistillation
from production.services.cvn_synthesis_service import CVNSynthesisService
from production.views.base_procedure_view import BaseProcedureView, BaseProcedureListView, BaseProcedureCreateView, \
    BaseProcedureUpdateView


class CVNDistillationBaseView(BaseProcedureView):
    # 子类必须覆盖的变量
    model = CVNDistillation
    form_class = CVNDistillationForm
    service_class = CVNSynthesisService
    template_name = 'production/procedure/cvn_distillation.html'
    reverse_str = 'production:cvn_distillation_update'
    batch_no_prefix = 'CVN-DIS'
    # 子类可选覆盖的变量
    require_source_batches = True  # 是否需要获取前置批次（精馏等工艺需要改为 True）

class CVNDistillationCreateView(CVNDistillationBaseView, BaseProcedureCreateView):
    pass

class CVNDistillationUpdateView(CVNDistillationBaseView, BaseProcedureUpdateView):
    pass

class CVNDistillationListView(CVNDistillationBaseView, BaseProcedureListView):
    template_name = 'production/procedure_list/procedure_list_cvn_distillation.html'