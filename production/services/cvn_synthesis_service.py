from production.services.base_procedure_service import BaseProcedureService

class CVNSynthesisService(BaseProcedureService):
    """
    CVN 合成工艺服务层 (重构版)
    所有标准投产、完工、校验与防守逻辑均继承自 BaseProcedureService。
    """
    # ==========================================
    # 工艺静态配置
    # ==========================================
    PROCEDURE_KEY = 'cvnsynthesis'

    # 注：CVN合成是源头工艺，直接领用原材料，无需配置前置批次 (SOURCE_BATCH_MODEL 等留空即可)

    # ==========================================
    # 钩子覆盖 (Hooks Overrides)
    # ==========================================
    @classmethod
    def _execute_inventory_addition(cls, instance, user):
        """
        覆写产出入库引擎。
        先执行基类的标准主产物入库，再处理特有的副产物 (DCB溶剂) 回收防丢逻辑。
        """
        # 1. 执行基类的标准主产物 (CVN粗品) 自动入库
        super()._execute_inventory_addition(instance, user)

        # 2. 兼容防丢逻辑：处理副产物回收
        # TODO: 拆分 DCB 回收工艺，或将其正式纳入 PROCEDURE_BOM_MAPPING 的 outputs 后，可直接删除整个 _execute_inventory_addition 方法！
        recovered_dcb = getattr(instance, 'recovered_dcb_amount', 0)
        if recovered_dcb and float(recovered_dcb) > 0:
            cls._update_single_stock(
                key='recycled_dcb',  # 对应回流的二氯丁烷字典key
                amount=float(recovered_dcb),
                note=f"批次 {instance.batch_no} 回收: DCB溶剂",
                user=user
            )