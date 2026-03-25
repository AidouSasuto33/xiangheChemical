from production.services.base_procedure_service import BaseProcedureService
from production.models.cvn_synthesis import CVNSynthesis

class CVNDistillationService(BaseProcedureService):
    """
    CVN 精馏工艺服务层 (重构极简版)
    极致纯净的子类，所有核心业务逻辑（含精前质检提取、前置批次溯源扣减等）
    均由 BaseProcedureService 底层引擎驱动。
    """
    # ==========================================
    # 1. 工艺身份标识
    # ==========================================
    PROCEDURE_KEY = 'cvndistillation'
    SOURCE_PROCEDURE_KEY = 'cvnsynthesis'

    # ==========================================
    # 2. 前置多批次溯源关联配置 (精馏强依赖前置合成粗品)
    # ==========================================
    SOURCE_BATCH_MODEL = CVNSynthesis                    # 前置来源模型：CVN合成
    SOURCE_CRUDE_WEIGHT_FIELD = 'cvn_syn_crude_weight'   # 来源模型的主产物字段，用于 F 表达式动态计算可用量
    INPUTS_RELATED_NAME = 'inputs'                       # 本模型子表 (CVNDistillationInput) 的反向查询名称
    SOURCE_GLOBAL_INVENTORY_KEY = 'cvn_syn_crude_weight' # 溯源扣减时，同步扣减的全局库存真实键名