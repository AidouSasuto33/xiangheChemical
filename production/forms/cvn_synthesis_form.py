from production.models.cvn_synthesis import CVNSynthesis
from .base_procedure_form import BaseProcedureForm

class CVNSynthesisForm(BaseProcedureForm):
    # === 1. 声明基类所需的配置属性 ===
    # 注意：此处保持与原 clean 方法中调用一致的 key ('cvnsynthesis')
    PROCEDURE_KEY = 'cvnsynthesis'
    MAIN_OUTPUT_FIELD = 'cvn_syn_crude_weight'

    INPUT_GROUP = [
        'start_time', 'expected_time', 'kettle',
        'raw_dcb', 'recycled_dcb', 'raw_nacn', 'raw_tbab', 'raw_alkali'
    ]

    OUTPUT_GROUP = [
        'end_time', 'cvn_syn_crude_weight',
        'recovered_dcb_amount', 'waste_batches'
    ]
    # 3. 质检闭环组 (化验室人员点击“录入质检”时必须填写的字段)
    QC_GROUP = [
        'test_time', 'content_cvn', 'content_dcb', 'content_adn'
    ]

    # 将 test_time 追加到基类的日期时间处理列表中，以便统一渲染 datetime-local 组件
    DATETIME_FIELDS = BaseProcedureForm.DATETIME_FIELDS + ['test_time']

    class Meta:
        model = CVNSynthesis
        fields = [
            'start_time', 'expected_time', 'end_time', 'kettle',
            'raw_dcb', 'recycled_dcb', 'raw_nacn', 'raw_tbab', 'raw_alkali',
            'cvn_syn_crude_weight', 'remarks',
            'test_time', 'content_cvn', 'content_dcb', 'content_adn', 'waste_batches'
        ]
