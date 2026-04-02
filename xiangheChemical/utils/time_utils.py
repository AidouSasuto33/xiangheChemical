from django.utils import timezone
from datetime import timedelta

def get_now_hour():
    """
    获取当前时间并抹除分钟及以下精度（即整点时间）。
    示例：2026-03-12 21:56 -> 2026-03-12 21:00
    """
    now = timezone.now()
    # 使用 replace 方法将分钟、秒和微秒全部归零
    return now.replace(minute=0, second=0, microsecond=0)

def get_default_start_time():
    """
    获取工单默认的开始时间：当前整点
    """
    return get_now_hour()

def get_default_expected_time():
    """
    获取工单默认的预计完成时间：当前整点 + 1天
    """
    return get_now_hour() + timedelta(days=1)

def format_duration(start_time, end_time):
    """
    辅助工具：格式化计算两个时间点的耗时（小时）
    """
    if end_time and start_time:
        delta = end_time - start_time
        return round(delta.total_seconds() / 3600, 1)
    return 0

def is_time_sequence_valid(earlier_time, later_time):
    """
    检查时间先后顺序。如果其中一个时间为空，则返回 True（由字段自身的 blank/null 约束处理）。
    """
    # 部分工艺没有test_time所以无法比较
    if not earlier_time or not later_time:
        return True

    return earlier_time <= later_time
