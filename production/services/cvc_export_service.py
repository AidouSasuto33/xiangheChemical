# production/services/cvc_export_service.py
from production.services.base_procedure_service import BaseProcedureService
from production.models.cvc_synthesis import CVCSynthesis


class CVCExportService(BaseProcedureService):
    """
    CVC 外销精制工艺服务层
    核心业务逻辑（含前置 CVC 成品质检提取、溯源扣减等）由底层引擎驱动。
    """
    # ==========================================
    # 1. 工艺身份标识
    # ==========================================
    PROCEDURE_KEY = 'cvcexport'
    SOURCE_PROCEDURE_KEY = 'cvcsynthesis'

    # ==========================================
    # 2. 前置多批次溯源关联配置 (强依赖前置 CVC 合格品)
    # ==========================================
    SOURCE_BATCH_MODEL = CVCSynthesis                    # 前置来源模型：CVC合成(内销)
    SOURCE_CRUDE_WEIGHT_FIELD = 'cvc_syn_crude_weight'   # 来源模型的主产物字段 (CVC合格品重量)
    INPUTS_RELATED_NAME = 'inputs'                       # 本模型子表反向查询名称
    SOURCE_GLOBAL_INVENTORY_KEY = 'cvc_syn_crude_weight' # 溯源扣减时的全局库存键名