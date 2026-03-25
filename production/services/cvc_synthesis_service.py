# production/services/cvc_synthesis_service.py
from production.services.base_procedure_service import BaseProcedureService
from production.models.cva_synthesis import CVASynthesis


class CVCSynthesisService(BaseProcedureService):
    """
    CVC 合成(内销) 工艺服务层
    极简子类，核心业务逻辑（含前置 CVA 质检提取、溯源扣减等）由底层引擎驱动。
    """
    # ==========================================
    # 1. 工艺身份标识
    # ==========================================
    PROCEDURE_KEY = 'cvcsynthesis'
    SOURCE_PROCEDURE_KEY = 'cvasynthesis'

    # ==========================================
    # 2. 前置多批次溯源关联配置 (强依赖前置 CVA 粗品)
    # ==========================================
    SOURCE_BATCH_MODEL = CVASynthesis                    # 前置来源模型：CVA合成
    SOURCE_CRUDE_WEIGHT_FIELD = 'cva_crude_weight'       # 来源模型的主产物字段
    INPUTS_RELATED_NAME = 'inputs'                       # 本模型子表反向查询名称
    SOURCE_GLOBAL_INVENTORY_KEY = 'cva_crude_weight'     # 溯源扣减时的全局库存键名