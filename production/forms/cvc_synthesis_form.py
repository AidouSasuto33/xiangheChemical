# production/forms/cvc_synthesis_form.py
from production.models.cvc_synthesis import CVCSynthesis, CVCSynthesisInput
from production.models.cva_synthesis import CVASynthesis
from .base_procedure_form import BaseProcedureForm


class CVCSynthesisForm(BaseProcedureForm):
    # === 1. 基础流程配置 ===
    PROCEDURE_KEY = 'cvc_synthesis'
    MAIN_OUTPUT_FIELD = 'cvc_syn_crude_weight'

    # 包含辅料二氯亚砜
    INPUT_GROUP = ['start_time', 'expected_time', 'kettle', 'raw_socl2']
    # 产出包含了合格品与前馏份(头酒)
    OUTPUT_GROUP = [
        'end_time', 'cvc_syn_crude_weight', 'distillation_head_weight',
        'content_cvc', 'content_cva'
    ]

    # === 2. 全局防篡改字段配置 ===
    READONLY_FIELDS = ['pre_content_cva', 'pre_content_cvn', 'pre_content_water']

    # === 3. 动态投入及多批次物料配置 (CVC合成特有) ===
    HAS_DYNAMIC_INPUTS = True
    SOURCE_BATCH_MODEL = CVASynthesis
    INPUT_RELATION_MODEL = CVCSynthesisInput
    INPUT_RELATION_FK_NAME = 'cvc_synthesis'
    TOTAL_INPUT_WEIGHT_FIELD = 'input_total_cva_weight'

    # 动态质检计算引擎映射: 目标字段(CVC精前) <- 来源字段(CVA产出)
    QC_SOURCE_MAP = {
        'pre_content_cva': 'content_cva',
        'pre_content_cvn': 'content_cvn',
        'pre_content_water': 'content_water',
    }

    class Meta:
        model = CVCSynthesis
        fields = [
            'start_time', 'expected_time', 'end_time', 'kettle',
            'raw_socl2',
            'pre_content_cva', 'pre_content_cvn', 'pre_content_water',
            'cvc_syn_crude_weight', 'distillation_head_weight',
            'content_cvc', 'content_cva',
        ]