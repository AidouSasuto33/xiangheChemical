from production.services.base_procedure_service import BaseProcedureService
from production.models.cvn_distillation import CVNDistillation

class CVASynthesisService(BaseProcedureService):
    """
    CVA 合成工艺服务层
    极简子类，核心业务逻辑（含精前质检提取、前置批次溯源扣减等）
    均由 BaseProcedureService 底层引擎驱动。
    """
    # ==========================================
    # 1. 工艺身份标识
    # ==========================================
    PROCEDURE_KEY = 'cvasynthesis'
    SOURCE_PROCEDURE_KEY = 'cvndistillation'

    # ==========================================
    # 2. 前置多批次溯源关联配置 (CVA合成强依赖前置CVN精馏精品)
    # ==========================================
    SOURCE_BATCH_MODEL = CVNDistillation                 # 前置来源模型：CVN精馏
    SOURCE_CRUDE_WEIGHT_FIELD = 'cvn_dis_crude_weight'   # 来源模型的主产物字段，用于 F 表达式动态计算可用量
    INPUTS_RELATED_NAME = 'inputs'                       # 本模型子表 (CVASynthesisInput) 的反向查询名称
    SOURCE_GLOBAL_INVENTORY_KEY = 'cvn_dis_crude_weight' # 溯源扣减时，同步扣减的全局库存真实键名