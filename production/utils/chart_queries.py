from django.db.models import Sum, Avg, Count


class BaseChartQuery:
    """
    通用图表查询引擎
    负责将业务 Model、时间切片与聚合指标转化为 ECharts 标准格式
    """

    def __init__(self, model, base_filters=None, time_field='start_time'):
        """
        :param model: Django Model 类 (如 ProductionLog)
        :param base_filters: 字典，基础过滤条件 (如 {'process_type': 'CVN', 'is_valid': True})
        :param time_field: 字符串，用于时间区间过滤的数据库字段名
        """
        self.model = model
        self.base_filters = base_filters or {}
        self.time_field = time_field

    def get_base_qs(self):
        """获取带有基础业务过滤的 QuerySet"""
        return self.model.objects.filter(**self.base_filters)

    def calculate_metric(self, qs, func, field, scale=1.0):
        """
        原子聚合计算
        包含数据补零 (Zero Filling) 与单位换算 (Unit Scaling)
        """
        if not field:
            return 0

        if func == 'SUM':
            val = qs.aggregate(res=Sum(field))['res']
        elif func == 'AVG':
            val = qs.aggregate(res=Avg(field))['res']
        elif func == 'COUNT':
            # COUNT 一般不需要 field，或者传 'id'
            val = qs.aggregate(res=Count(field))['res']
        else:
            val = 0

        # 处理数据库返回 None 的情况（补零）
        val = val if val is not None else 0

        # 乘以缩放系数并保留两位小数（例如克转吨，scale=0.001）
        return round(val * scale, 2)

    def fetch_trend_series(self, time_slices, metrics_config):
        """
        生成趋势图/柱状图数据 (适用于多个时间切片的组合)

        :param time_slices: List[Dict]，来自 charts_time_utils 生成的切片
        :param metrics_config: List[Dict]，指标配置。例如：
            [
                {'key': 'yield', 'name': '产量(吨)', 'func': 'SUM', 'field': 'output_weight', 'scale': 0.001},
                {'key': 'cost', 'name': '吨产成本', 'func': 'AVG', 'field': 'unit_cost', 'scale': 1}
            ]
        :return: Dict 格式，直接适配 ECharts
        """
        chart_data = {
            'xAxis': [],
            # 预先构建好 ECharts 的 series 骨架
            'series_map': {
                m['key']: {'name': m['name'], 'type': m.get('type', 'line'), 'data': []}
                for m in metrics_config
            }
        }

        base_qs = self.get_base_qs()

        # 遍历时间切片，进行循环查询
        for t_slice in time_slices:
            chart_data['xAxis'].append(t_slice['label'])

            # 组装时间范围过滤条件：如 {'created_at__range': (start, end)}
            time_filter = {f"{self.time_field}__range": (t_slice['start'], t_slice['end'])}
            current_qs = base_qs.filter(**time_filter)

            # 计算该时间切片下的所有指标
            for m in metrics_config:
                val = self.calculate_metric(
                    qs=current_qs,
                    func=m.get('func'),
                    field=m.get('field'),
                    scale=m.get('scale', 1.0)
                )
                chart_data['series_map'][m['key']]['data'].append(val)

        # 扁平化输出，剥离字典键，还原为 ECharts 要求的 list 结构
        chart_data['series'] = list(chart_data['series_map'].values())
        del chart_data['series_map']

        return chart_data