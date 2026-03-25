from datetime import timedelta
from django.utils import timezone
from dateutil.relativedelta import relativedelta

# 单位常量定义
UNIT_DAY = 'day'
UNIT_WEEK = 'week'
UNIT_MONTH = 'month'
UNIT_QUARTER = 'quarter'
UNIT_YEAR = 'year'


def get_unit_window(unit, ref_date=None, to_date=False):
    """
    原子层：获取单个时间单位的起止时间。
    to_date=True 时，结束时间将锁定在 ref_date 的时刻（用于公平环比）。
    """
    if not ref_date:
        ref_date = timezone.now()

    # 确保是 aware datetime
    if timezone.is_naive(ref_date):
        ref_date = timezone.make_aware(ref_date)

    if unit == UNIT_DAY:
        start = ref_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = ref_date if to_date else start + timedelta(days=1)

    elif unit == UNIT_WEEK:
        # 以周一为起始（Monday=0）
        start = (ref_date - timedelta(days=ref_date.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = ref_date if to_date else start + timedelta(weeks=1)

    elif unit == UNIT_MONTH:
        start = ref_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = ref_date if to_date else start + relativedelta(months=1)

    elif unit == UNIT_QUARTER:
        # 计算季度起始月份：1, 4, 7, 10
        quarter_start_month = ((ref_date.month - 1) // 3) * 3 + 1
        start = ref_date.replace(month=quarter_start_month, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = ref_date if to_date else start + relativedelta(months=3)

    elif unit == UNIT_YEAR:
        start = ref_date.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = ref_date if to_date else start + relativedelta(years=1)

    else:
        raise ValueError(f"Unsupported unit: {unit}")

    return start, end


def get_offset_window(unit, offset=1, ref_date=None, to_date=False):
    """
    偏移层：获取相对于基准时间偏移 N 个周期的窗口。
    """
    if not ref_date:
        ref_date = timezone.now()

    # 计算偏移后的基准点
    delta_kwargs = {f"{unit}s": -offset} if unit != UNIT_QUARTER else {"months": -offset * 3}
    offset_ref_date = ref_date + relativedelta(**delta_kwargs)

    # 处理 To-Date 的边界溢出（例如 3月31日的上个月是 2月28/29日）
    # relativedelta 已经帮我们处理了这种逻辑

    return get_unit_window(unit, ref_date=offset_ref_date, to_date=to_date)


def generate_time_slices(unit, intervals=12, ref_date=None):
    """
    切片层：生成 11+1 模式的连续时间切片。
    """
    if not ref_date:
        ref_date = timezone.now()

    slices = []
    # 从当前(或指定)时刻所属的完整周期开始倒推
    for i in range(intervals - 1, -1, -1):
        delta_kwargs = {f"{unit}s": -i} if unit != UNIT_QUARTER else {"months": -i * 3}
        target_ref = ref_date + relativedelta(**delta_kwargs)

        # 最后一个切片（即当前周期）需要 to_date 截断
        is_current_slice = (i == 0)
        start, end = get_unit_window(unit, ref_date=target_ref, to_date=is_current_slice)

        # 生成前端 Label
        label = _get_slice_label(unit, start, is_current_slice)

        slices.append({
            'label': label,
            'start': start,
            'end': end,
            'is_current': is_current_slice
        })
    return slices


def _get_slice_label(unit, dt, is_current):
    """内部辅助：生成可读性强的 Label"""
    if unit == UNIT_DAY:
        return dt.strftime('%m-%d')
    elif unit == UNIT_WEEK:
        return f"W{dt.strftime('%V')}"  # ISO 周号
    elif unit == UNIT_MONTH:
        return dt.strftime('%Y-%m')
    elif unit == UNIT_QUARTER:
        quarter = (dt.month - 1) // 3 + 1
        return f"{dt.year} Q{quarter}"
    return dt.strftime('%Y')


def get_dashboard_time_config(unit, intervals=12, comparison_mode=None, ref_date=None, compare_ref_date=None):
    """
    调度层：面向业务的大函数。
    comparison_mode: 'POP' (环比), 'TOP' (同比), 'CUSTOM' (自定义对比)
    """
    if not ref_date:
        ref_date = timezone.now()

    # 1. 获取主序列（用于走势图）
    main_slices = generate_time_slices(unit, intervals, ref_date)

    # 2. 获取对比范围
    compare_window = None
    if comparison_mode == 'POP':
        # 环比：自动开启 To-Date
        compare_window = get_offset_window(unit, offset=1, ref_date=ref_date, to_date=True)
    elif comparison_mode == 'TOP':
        # 同比：向前推一年（若单位是月，offset=12；若单位是季，offset=4）
        offset = 12 if unit == UNIT_MONTH else (4 if unit == UNIT_QUARTER else 1)
        compare_window = get_offset_window(unit, offset=offset, ref_date=ref_date, to_date=True)
    elif comparison_mode == 'CUSTOM' and compare_ref_date:
        # 自定义对比：通常取全周期
        compare_window = get_unit_window(unit, ref_date=compare_ref_date, to_date=False)

    return {
        'unit': unit,
        'main_slices': main_slices,
        'compare_window': compare_window,  # (start, end)
        'summary_label': main_slices[-1]['label']
    }