from django.http import JsonResponse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from ...services.partial.labor_record_service import LaborRecordService

class LaborUpdateView(LoginRequiredMixin, View):
    """单条人工记录异步保存/更新"""
    def post(self, request, *args, **kwargs):
        # 提取 Ajax 发送的数据
        data = {
            'id': request.POST.get('id'),
            'cost_config_id': request.POST.get('cost_config_id'),
            'worker_count': request.POST.get('worker_count'),
            'work_hours': request.POST.get('work_hours'),
            'record_date': request.POST.get('record_date'),
        }
        batch_no = request.POST.get('batch_no')
        procedure_type = request.POST.get('procedure_type')

        try:
            record_id = LaborRecordService.update_single_record(batch_no, procedure_type, data)
            return JsonResponse({'status': 'success', 'record_id': record_id})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

class LaborDeleteView(LoginRequiredMixin, View):
    """单条人工记录异步物理删除"""
    def post(self, request, *args, **kwargs):
        record_id = request.POST.get('id')
        batch_no = request.POST.get('batch_no')

        if LaborRecordService.delete_single_record(record_id, batch_no):
            return JsonResponse({'status': 'success'})
        else:
            return JsonResponse({'status': 'error', 'message': '删除失败或无权限'}, status=400)