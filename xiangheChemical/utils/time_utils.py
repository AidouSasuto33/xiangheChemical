# production/utils/time_utils.py
from django.utils import timezone
from datetime import timedelta

def get_default_expected_time():
    """
    获取默认的预计完成时间：当前时间加 1 天。
    未来可以在此扩展更复杂的逻辑，例如根据特定工艺（Procedure Type）自动计算标准工时。
    """
    # 返回当前时间加 1 天
    return timezone.now() + timedelta(days=1)

def format_duration(start_time, end_time):
    """
    辅助工具：格式化计算两个时间点的耗时（小时）
    """
    if end_time and start_time:
        delta = end_time - start_time
        return round(delta.total_seconds() / 3600, 1)
    return 0