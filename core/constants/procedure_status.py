from django.db import models
from django.utils.translation import gettext_lazy as _

class ProcedureState(models.TextChoices):
    """
    工单生产状态常量 (Static States)
    代表工单当前所处的阶段
    """
    NEW = 'new', _('新工单')
    RUNNING = 'running', _('生产中')
    DELAYED = 'delayed', _('已延迟')
    ABNORMAL = 'abnormal', _('异常单')
    COMPLETED = 'completed', _('已完成')


class ProcedureAction(models.TextChoices):
    """
    工单操作动作常量 (Dynamic Actions)
    代表触发状态流转或数据保存的动作
    """
    CREATE_PLAN = 'create_plan', _('创建工单')
    SAVE_DRAFT = 'save_draft', _('保存修改')
    START_PRODUCTION = 'start_production', _('开始投产')
    FINISH_PRODUCTION = 'finish_production', _('完成生产')
    PAUSE_ABNORMAL_PRODUCTION = 'pause_abnormal_production', _('报告异常/暂停')
    RESUME_ABNORMAL_PRODUCTION = 'resume_abnormal_production', _('恢复正常生产')
    DELAYED_PRODUCTION = 'delayed_production', _('标记延迟')