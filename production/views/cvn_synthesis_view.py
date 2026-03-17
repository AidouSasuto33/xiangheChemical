from production.forms import CVNSynthesisForm
from production.models import CVNSynthesis
from production.services.cvn_synthesis_service import CVNSynthesisService
from production.views.base_procedure_view import BaseProcedureCreateView, BaseProcedureView, BaseProcedureUpdateView, \
    BaseProcedureListView


class CVNSynthesisBaseView(BaseProcedureView):
    # 子类必须覆盖的变量
    model = CVNSynthesis
    form_class = CVNSynthesisForm
    service_class = CVNSynthesisService
    template_name = 'production/procedure/cvn_synthesis.html'
    reverse_str = 'production:cvn_synthesis_update'  # 例如: 'production:cvn_synthesis_update'
    batch_no_prefix = 'CVN-SYN'  # 例如: 'CVN-SYN'

class CVNSynthesisCreateView(CVNSynthesisBaseView, BaseProcedureCreateView ):
    pass

class CVNSynthesisUpdateView(CVNSynthesisBaseView, BaseProcedureUpdateView ):
    pass

class CVNSynthesisListView(CVNSynthesisBaseView, BaseProcedureListView):
    template_name = 'production/procedure_list/procedure_list_cvn_synthesis.html'