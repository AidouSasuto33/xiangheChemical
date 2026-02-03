from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from production.models.kettle import Kettle

class KettleDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'production/kettle/kettle_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        # 获取所有釜皿
        all_kettles = Kettle.objects.all()
        
        # 分组
        running_kettles = []
        cleaning_kettles = []
        idle_kettles = []
        maintenance_kettles = []
        
        for kettle in all_kettles:
            if kettle.status == Kettle.STATUS_RUNNING:
                running_kettles.append(kettle)
            elif kettle.status == Kettle.STATUS_CLEANING:
                cleaning_kettles.append(kettle)
            elif kettle.status == Kettle.STATUS_IDLE:
                idle_kettles.append(kettle)
            elif kettle.status == Kettle.STATUS_MAINTENANCE:
                maintenance_kettles.append(kettle)
        
        # 排序函数
        def sort_kettles(kettle_list):
            return sorted(kettle_list, key=lambda k: (k.workshop or '', k.name))
            
        context['running_kettles'] = sort_kettles(running_kettles)
        context['cleaning_kettles'] = sort_kettles(cleaning_kettles)
        context['idle_kettles'] = sort_kettles(idle_kettles)
        context['maintenance_kettles'] = sort_kettles(maintenance_kettles)
        
        return context
