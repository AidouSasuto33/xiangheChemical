from core.constants.procedure_status import ProcedureState, ProcedureAction
from production.services.partial.kettle_state_service import KettleStateService
from production.signals import post_procedure_state_change  # 新增：导入状态变更信号


class ProcedureStateService:
    """
    工单状态机服务
    负责统一处理所有工单的状态流转逻辑、前置校验以及关联设备(Kettle)的状态联动
    """

    @classmethod
    def process_action(cls, procedure, action, **kwargs):
        """
        统一动作分发入口
        :param procedure: 工单实例 (BaseProcedure 的子类实例)
        :param action: ProcedureAction 常量
        """
        action_map = {
            ProcedureAction.CREATE_PLAN: cls.create_plan,
            ProcedureAction.SAVE_DRAFT: cls.save_draft,
            ProcedureAction.START_PRODUCTION: cls.start_production,
            ProcedureAction.FINISH_PRODUCTION: cls.finish_production,
            ProcedureAction.PAUSE_ABNORMAL_PRODUCTION: cls.pause_abnormal_production,
            ProcedureAction.RESUME_ABNORMAL_PRODUCTION: cls.resume_abnormal_production,
            ProcedureAction.DELAYED_PRODUCTION: cls.delayed_production,
        }

        if action not in action_map:
            raise ValueError(f"未知的工单操作动作: {action}")

        # 记录流转前的状态
        old_status = procedure.status

        # 执行具体的状态动作方法
        result = action_map[action](procedure, **kwargs)

        # 获取流转后的新状态
        new_status = procedure.status

        # 仅当状态发生实质性变化时，才发射信号给消息通知模块
        if old_status != new_status:
            post_procedure_state_change.send(
                sender=procedure.__class__,
                instance=procedure,
                old_status=old_status,
                new_status=new_status,
                user=kwargs.get('user')  # 从 kwargs 提取当前操作人
            )

        return result

    @classmethod
    def create_plan(cls, procedure, **kwargs):
        """创建工单：通常由视图层初始化，这里做防呆保护"""
        if not procedure.status:
            procedure.status = ProcedureState.NEW
        procedure.save()
        return procedure

    @classmethod
    def save_draft(cls, procedure, **kwargs):
        """保存草稿/记录：不改变现有状态，仅保存数据"""
        procedure.save()
        return procedure

    @classmethod
    def start_production(cls, procedure, **kwargs):
        """开始投产：只能从 新建 状态变更为 生产中"""
        if procedure.status != ProcedureState.NEW:
            raise ValueError(f"状态冲突：无法从 {procedure.get_status_display()} 状态直接开始投产")

        procedure.status = ProcedureState.RUNNING
        procedure.save()

        # 联动设备状态：占用设备进行生产
        kettle = getattr(procedure, 'kettle', None)
        if kettle:
            KettleStateService.occupy_for_production(kettle)

        return procedure

    @classmethod
    def finish_production(cls, procedure, **kwargs):
        """完成生产：只能从 生产中 或 已延迟 状态变更为 已完成"""
        allowed_states = [ProcedureState.RUNNING, ProcedureState.DELAYED]
        if procedure.status not in allowed_states:
            raise ValueError(f"状态冲突：当前 {procedure.get_status_display()} 状态无法直接标记为完成")

        procedure.status = ProcedureState.COMPLETED
        procedure.save()

        # 联动设备状态：释放设备至待清洁状态
        kettle = getattr(procedure, 'kettle', None)
        if kettle:
            KettleStateService.release_to_clean(kettle)

        return procedure

    @classmethod
    def pause_abnormal_production(cls, procedure, **kwargs):
        """报告异常：中止当前生产或延迟状态"""
        allowed_states = [ProcedureState.RUNNING, ProcedureState.DELAYED]
        if procedure.status not in allowed_states:
            raise ValueError(f"状态冲突：当前 {procedure.get_status_display()} 状态无法报告异常")

        procedure.status = ProcedureState.ABNORMAL
        procedure.save()

        # 联动设备状态：工单异常中断，强制设备转入维护/故障状态
        kettle = getattr(procedure, 'kettle', None)
        if kettle:
            KettleStateService.report_abnormal_maintenance(kettle)

        return procedure

    @classmethod
    def resume_abnormal_production(cls, procedure, **kwargs):
        """恢复正常生产：只能从 异常 状态恢复到 生产中"""
        if procedure.status != ProcedureState.ABNORMAL:
            raise ValueError(f"状态冲突：当前工单并非异常状态，无法执行恢复操作")

        procedure.status = ProcedureState.RUNNING
        procedure.save()

        # 联动设备状态：先解除设备的维护状态，再重新占用投产
        kettle = getattr(procedure, 'kettle', None)
        if kettle:
            KettleStateService.finish_maintenance(kettle)
            KettleStateService.occupy_for_production(kettle)

        return procedure

    @classmethod
    def delayed_production(cls, procedure, **kwargs):
        """标记延迟：将正常进行中的工单标记为延迟"""
        if procedure.status != ProcedureState.RUNNING:
            raise ValueError(f"状态冲突：只能将正常生产中的工单标记为延迟")

        procedure.status = ProcedureState.DELAYED
        procedure.save()

        # 延迟状态不改变设备的物理占用和运行状态，因此无需调用 KettleStateService
        return procedure