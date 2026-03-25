# production/forms/cvn_distillation_form.py
from django.core.exceptions import ValidationError
from production.models.cvn_distillation import CVNDistillation, CVNDistillationInput
from production.models.cvn_synthesis import CVNSynthesis
from .base_procedure_form import BaseProcedureForm


class CVNDistillationForm(BaseProcedureForm):
    # === 1. 基础流程配置 ===
    PROCEDURE_KEY = 'cvndistillation'
    MAIN_OUTPUT_FIELD = 'cvn_dis_crude_weight'

    INPUT_GROUP = ['start_time', 'expected_time', 'kettle']
    OUTPUT_GROUP = [
        'end_time', 'cvn_dis_crude_weight',
        'output_content_cvn', 'output_content_dcb', 'output_content_adn',
        'residue_weight'
    ]

    # === 2. 全局防篡改字段配置 ===
    READONLY_FIELDS = ['pre_content_cvn', 'pre_content_dcb', 'pre_content_adn']

    # === 3. 动态投入及多批次物料配置 (精馏特有) ===
    HAS_DYNAMIC_INPUTS = True
    SOURCE_BATCH_MODEL = CVNSynthesis
    INPUT_RELATION_MODEL = CVNDistillationInput
    INPUT_RELATION_FK_NAME = 'distillation'
    TOTAL_INPUT_WEIGHT_FIELD = 'input_total_cvn_weight'

    QC_SOURCE_MAP = {
        'pre_content_cvn': 'content_cvn',
        'pre_content_dcb': 'content_dcb',
        'pre_content_adn': 'content_adn',
    }

    class Meta:
        model = CVNDistillation
        fields = [
            'start_time', 'expected_time', 'end_time', 'kettle',
            'pre_content_cvn', 'pre_content_dcb', 'pre_content_adn',
            'cvn_dis_crude_weight', 'output_content_cvn', 'output_content_dcb', 'output_content_adn',
            'residue_weight',
        ]

    # === 4. 局部特性校验 ===
    # 保留精馏工序特有的釜残重量校验，因为其允许为0但不允许留空的业务逻辑有别于主产物
    def clean_residue_weight(self):
        weight = self.cleaned_data.get('residue_weight')
        if self.action_type == 'finish_production':
            if weight is None or weight < 0:
                raise ValidationError("确认完工时，必须填写釜残重量（若无釜残请填 0）。")
        return weight