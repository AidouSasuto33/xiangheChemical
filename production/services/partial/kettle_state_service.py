from production.models.kettle import Kettle
from core.constants.kettle_status import KettleState


class KettleStateService:
    """
    釜皿/设备状态机服务
    负责统一处理釜皿自身的独立状态流转逻辑和前置校验
    """

    # ==========================================
    # 类别一：独立操作 (主要由 Kettle Dashboard 触发)
    # ==========================================

    @classmethod
    def mark_cleaned(cls, kettle, **kwargs):
        """完成清洁：从 待清洁(to_clean) 状态变更为 空闲(idle)"""
        if kettle.status != KettleState.CLEANING:
            raise ValueError(f"状态冲突：釜皿 {kettle.name} 当前不在待清洁状态，无法执行完成清洁操作")

        kettle.status = KettleState.IDLE
        kettle.save()
        return kettle

    @classmethod
    def start_maintenance(cls, kettle, **kwargs):
        """开始维护：将非生产中的釜皿变更为 维护/故障(maintenance)"""
        # 防止把正在生产中的釜皿强行变成维护状态，必须先暂停关联的工单
        if kettle.status == KettleState.RUNNING:
            raise ValueError(f"状态冲突：釜皿 {kettle.name} 正在生产中，请先处理关联的生产工单")

        kettle.status = KettleState.MAINTENANCE
        kettle.save()
        return kettle

    @classmethod
    def finish_maintenance(cls, kettle, **kwargs):
        """结束维护：从 维护/故障(maintenance) 状态恢复为 空闲(idle)"""
        if kettle.status != KettleState.MAINTENANCE:
            raise ValueError(f"状态冲突：釜皿 {kettle.name} 当前不在维护状态，无法执行结束维护操作")

        kettle.status = KettleState.IDLE
        kettle.save()
        return kettle

    # ==========================================
    # 类别二：生产联动操作 (主要由 ProcedureStateService 调用)
    # ==========================================

    @classmethod
    def occupy_for_production(cls, kettle, **kwargs):
        """被工单占用投产：从 空闲(idle) 变更为 生产中(running)"""
        if kettle.status != KettleState.IDLE:
            raise ValueError(
                f"状态冲突：釜皿 {kettle.name} 当前并非空闲状态 ({kettle.get_status_display()})，无法投料生产")

        kettle.status = KettleState.RUNNING
        kettle.save()
        return kettle

    @classmethod
    def release_to_clean(cls, kettle, **kwargs):
        """释放并待清洁：工单正常完成时，从 生产中(running) 变更为 待清洁(to_clean)"""
        if kettle.status != KettleState.RUNNING:
            raise ValueError(f"状态冲突：釜皿 {kettle.name} 当前并非生产中，无法正常释放")

        kettle.status = KettleState.CLEANING
        kettle.save()
        return kettle

    @classmethod
    def report_abnormal_maintenance(cls, kettle, **kwargs):
        """异常中止：工单报告异常导致中断，设备强制转为 维护/故障(maintenance)"""
        if kettle.status != KettleState.RUNNING:
            raise ValueError(f"状态冲突：釜皿 {kettle.name} 并非生产中，无法因异常直接转入维护")

        kettle.status = KettleState.MAINTENANCE
        kettle.save()
        return kettle