from django.db import models
from django.utils.translation import gettext_lazy as _


class KettleState(models.TextChoices):
    """
    釜皿/设备静态状态常量 (Static States)
    代表物理设备当前所处的实际客观状态
    """
    IDLE = 'idle', _('🟢 空闲 (可使用)')
    RUNNING = 'running', _('🔴 生产中')
    CLEANING = 'to_clean', _('🟡 待清洁')
    MAINTENANCE = 'maintenance', _('⚪ 维护/故障')


class KettleAction(models.TextChoices):
    """
    釜皿操作动作常量 (Dynamic Actions)
    用于触发设备状态的流转
    """
    # === 类别一：独立日常操作 (由 Kettle Dashboard 触发) ===
    MARK_CLEANED = 'mark_cleaned', _('完成清洁')
    START_MAINTENANCE = 'start_maintenance', _('开始维护/报修')
    FINISH_MAINTENANCE = 'finish_maintenance', _('结束维护/恢复空闲')

    # === 类别二：生产被动联动操作 (由 ProcedureStateService 触发) ===
    OCCUPY_FOR_PRODUCTION = 'occupy_for_production', _('被工单占用投产')
    RELEASE_TO_CLEAN = 'release_to_clean', _('工单完工释放待洗')
    REPORT_ABNORMAL = 'report_abnormal', _('工单异常强制转维护')