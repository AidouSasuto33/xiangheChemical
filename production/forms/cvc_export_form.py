# production/forms/cvc_export_form.py
from production.models.cvc_export import CVCExport, CVCExportInput
from production.models.cvc_synthesis import CVCSynthesis
from .base_procedure_form import BaseProcedureForm


class CVCExportForm(BaseProcedureForm):
    # === 1. 基础流程配置 ===
    PROCEDURE_KEY = 'cvcexport'
    MAIN_OUTPUT_FIELD = 'cvc_dis_crude_weight'

    # 仅需釜皿等基础投入，无额外辅料
    INPUT_GROUP = ['start_time', 'expected_time', 'kettle']
    OUTPUT_GROUP = [
        'end_time', 'cvc_dis_crude_weight',
        'content_cvc', 'content_cva'
    ]

    # === 2. 全局防篡改字段配置 ===
    READONLY_FIELDS = ['pre_content_cvc', 'pre_content_cva']

    # === 3. 动态投入及多批次物料配置 (CVC外销特有) ===
    HAS_DYNAMIC_INPUTS = True
    SOURCE_BATCH_MODEL = CVCSynthesis
    INPUT_RELATION_MODEL = CVCExportInput
    INPUT_RELATION_FK_NAME = 'cvc_export'
    TOTAL_INPUT_WEIGHT_FIELD = 'input_total_cvc_weight'

    # 动态质检计算引擎映射: 目标字段(外销精前) <- 来源字段(CVC成品产出)
    QC_SOURCE_MAP = {
        'pre_content_cvc': 'content_cvc',
        'pre_content_cva': 'content_cva',
    }

    class Meta:
        model = CVCExport
        fields = [
            'start_time', 'expected_time', 'end_time', 'kettle',
            'pre_content_cvc', 'pre_content_cva',
            'cvc_dis_crude_weight', 'content_cvc', 'content_cva',
        ]