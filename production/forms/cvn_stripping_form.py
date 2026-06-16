# production/forms/cvn_stripping_form.py
from django.core.exceptions import ValidationError
from production.models.cvn_stripping import CVNStripping, CVNStrippingInput
from production.models.cvn_synthesis import CVNSynthesis
from .base_procedure_form import BaseProcedureForm

class CVNStrippingForm(BaseProcedureForm):
    # === 1. 基础流程配置 ===
    PROCEDURE_KEY = 'cvnstripping'
    MAIN_OUTPUT_FIELD = 'cvn_str_crude_weight'

    INPUT_GROUP = ['start_time', 'expected_time', 'kettle']
    OUTPUT_GROUP = [
        'end_time', 'cvn_str_crude_weight', 'recycled_dcb'
    ]
    QC_GROUP = ['output_content_cvn', 'output_content_dcb', 'output_content_adn', 'test_time']

    # === 2. 全局防篡改字段配置 ===
    READONLY_FIELDS = ['pre_content_cvn', 'pre_content_dcb', 'pre_content_adn', 'recycled_dcb_purity']

    # === 3. 动态投入及多批次物料配置 (粗蒸特有) ===
    HAS_DYNAMIC_INPUTS = True
    SOURCE_BATCH_MODEL = CVNSynthesis
    INPUT_RELATION_MODEL = CVNStrippingInput
    INPUT_RELATION_FK_NAME = 'stripping'
    TOTAL_INPUT_WEIGHT_FIELD = 'input_total_cvn_weight'

    QC_SOURCE_MAP = {
        'pre_content_cvn': 'content_cvn',
        'pre_content_dcb': 'content_dcb',
        'pre_content_adn': 'content_adn',
    }

    class Meta:
        model = CVNStripping
        fields = [
            'start_time', 'expected_time', 'end_time', 'kettle',
            'pre_content_cvn', 'pre_content_dcb', 'pre_content_adn',
            'cvn_str_crude_weight', 'recycled_dcb', 'recycled_dcb_purity',
            'output_content_cvn', 'output_content_dcb', 'output_content_adn', 'test_time', 'remarks'
        ]