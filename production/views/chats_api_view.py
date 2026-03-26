import json
from django.http import JsonResponse
from django.views import View
from django.shortcuts import render

from production.utils.charts_time_utils import get_dashboard_time_config
from production.utils.chart_queries import BaseChartQuery
from production.constants.chart_registry import DATASET_REGISTRY

class ChartAPIView(View):
    """
    数据大盘通用查询网关
    接收前端动态参数，返回标准的 ECharts 数据结构
    """
    template_name = 'production/charts/charts_entry.html'

    def get(self, request, *args, **kwargs):
        """处理页面访问"""
        return render(request, self.template_name)

    def post(self, request, *args, **kwargs):
        try:
            # 1. 解析前端传递的动态参数
            payload = json.loads(request.body)
            dataset_key = payload.get('dataset')  # 如 'cvn_production'
            unit = payload.get('unit', 'week')  # 周期 (日/周/月/季)
            intervals = int(payload.get('intervals', 12))  # 周期数
            ref_date = payload.get('ref_date', None)  # 基准日期
            metrics = payload.get('metrics', [])  # 指标配置列表
            is_stacked = payload.get('is_stacked', False)  # 是否开启堆叠 (你的前端分类)

            # 2. 安全校验
            if dataset_key not in DATASET_REGISTRY:
                return JsonResponse({'code': 400, 'error': '未知的业务数据集'})
            if not metrics:
                return JsonResponse({'code': 400, 'error': '未提供指标配置'})

            # 3. 提取注册表配置
            ds_config = DATASET_REGISTRY[dataset_key]

            # 4. 生成时间切片
            time_info = get_dashboard_time_config(unit=unit, intervals=intervals, ref_date=ref_date)

            # 5. 实例化查询引擎
            engine = BaseChartQuery(
                model=ds_config['model'],
                base_filters=ds_config['base_filters'],
                time_field=ds_config['time_field']
            )

            # 6. 执行查询
            chart_data = engine.fetch_trend_series(
                time_slices=time_info['main_slices'],
                metrics_config=metrics
            )

            # 7. 动态应用前端的图形分类 (如堆叠)
            if is_stacked:
                for series_item in chart_data['series']:
                    series_item['stack'] = 'Total'


            return JsonResponse({
                'code': 200,
                'data': {
                    'summary_label': time_info['summary_label'],
                    'chart_data': chart_data
                }
            })

        except Exception as e:
            # 实际生产环境建议接入 logging
            return JsonResponse({'code': 500, 'error': str(e)})