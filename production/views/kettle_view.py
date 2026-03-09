from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.contrib import messages

from production.models.kettle import Kettle
# 引入釜皿状态机常量与服务
from core.constants.kettle_status import KettleState, KettleAction
from production.services.partial.kettle_state_service import KettleStateService


class KettleDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'production/kettle/kettle_dashboard.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # 获取所有釜皿
        all_kettles = Kettle.objects.all()

        # 初始化分组
        running_kettles = []
        cleaning_kettles = []
        idle_kettles = []
        maintenance_kettles = []

        # 根据最新的 KettleState 枚举进行分组
        for kettle in all_kettles:
            if kettle.status == KettleState.RUNNING:
                running_kettles.append(kettle)
            elif kettle.status == KettleState.CLEANING:
                cleaning_kettles.append(kettle)
            elif kettle.status == KettleState.IDLE:
                idle_kettles.append(kettle)
            elif kettle.status == KettleState.MAINTENANCE:
                maintenance_kettles.append(kettle)

        # 排序函数：优先按车间排序，再按名称排序
        def sort_kettles(kettle_list):
            return sorted(kettle_list, key=lambda k: (k.workshop or '', k.name))

        context['running_kettles'] = sort_kettles(running_kettles)
        context['cleaning_kettles'] = sort_kettles(cleaning_kettles)
        context['idle_kettles'] = sort_kettles(idle_kettles)
        context['maintenance_kettles'] = sort_kettles(maintenance_kettles)

        # 将 Action 常量传入模板，方便前端按钮直接绑定 value
        context['KettleAction'] = KettleAction

        return context

    def post(self, request, *args, **kwargs):
        """
        统一处理仪表盘上的釜皿独立状态变更请求
        """
        action = request.POST.get('action')
        kettle_id = request.POST.get('kettle_id')

        if not kettle_id:
            messages.error(request, "操作失败：未提供明确的釜皿ID！")
            return redirect(request.path)

        try:
            kettle = Kettle.objects.get(id=kettle_id)

            # === 动作路由分发 ===
            if action == KettleAction.MARK_CLEANED:
                KettleStateService.mark_cleaned(kettle)
                messages.success(request, f"✅ 釜皿 {kettle.name} 已完成清洁，现处于空闲可用状态。")

            elif action == KettleAction.START_MAINTENANCE:
                KettleStateService.start_maintenance(kettle)
                messages.warning(request, f"🔧 釜皿 {kettle.name} 已转入维护/故障状态。")

            elif action == KettleAction.FINISH_MAINTENANCE:
                KettleStateService.finish_maintenance(kettle)
                messages.success(request, f"✅ 釜皿 {kettle.name} 维护结束，已恢复空闲。")

            else:
                messages.error(request, f"❌ 拒绝执行：未知的操作指令 '{action}'。")

        except Kettle.DoesNotExist:
            messages.error(request, "❌ 操作失败：在数据库中找不到对应的设备！")
        except ValueError as e:
            # 捕获 Service 层抛出的状态冲突等业务异常 (如: 试图维护正在生产中的设备)
            messages.error(request, f"⚠️ {str(e)}")

        # 操作完成后重定向回仪表盘，刷新状态
        return redirect(request.path)