from production.models.cva_synthesis import CVASynthesis, CVASynthesisInput
from production.models.cvn_distillation import CVNDistillation
from .base_procedure_form import BaseProcedureForm


class CVASynthesisForm(BaseProcedureForm):
    # === 1. 基础流程配置 ===
    PROCEDURE_KEY = 'cvasynthesis'
    MAIN_OUTPUT_FIELD = 'cva_crude_weight'

    # 加入了合成工艺特有的辅料投入
    INPUT_GROUP = ['start_time', 'expected_time', 'kettle', 'raw_hcl', 'raw_alkali']
    OUTPUT_GROUP = [
        'end_time', 'cva_crude_weight',
        'content_cva', 'content_cvn', 'content_water'
    ]

    # === 2. 全局防篡改字段配置 ===
    READONLY_FIELDS = ['pre_content_cvn', 'pre_content_dcb', 'pre_content_adn']

    # === 3. 动态投入及多批次物料配置 (CVA合成特有) ===
    HAS_DYNAMIC_INPUTS = True
    SOURCE_BATCH_MODEL = CVNDistillation
    INPUT_RELATION_MODEL = CVASynthesisInput
    INPUT_RELATION_FK_NAME = 'cva_synthesis'
    TOTAL_INPUT_WEIGHT_FIELD = 'input_total_cvc_dis_weight'  # 对应模型中的字段名

    # 动态质检计算引擎映射: 目标字段(CVA精前) <- 来源字段(CVN精馏产出)
    QC_SOURCE_MAP = {
        'pre_content_cvn': 'output_content_cvn',
        'pre_content_dcb': 'output_content_dcb',
        'pre_content_adn': 'output_content_adn',
    }

    class Meta:
        model = CVASynthesis
        fields = [
            'start_time', 'expected_time', 'end_time', 'kettle',
            'raw_hcl', 'raw_alkali',
            'pre_content_cvn', 'pre_content_dcb', 'pre_content_adn',
            'cva_crude_weight', 'content_cva', 'content_cvn', 'content_water',
        ]