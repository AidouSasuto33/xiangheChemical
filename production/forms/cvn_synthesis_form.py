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
        'end_time', 'test_time', 'cvn_syn_crude_weight',
        'content_cvn', 'content_dcb', 'content_adn',
        'recovered_dcb_amount', 'waste_batches'
    ]

    # 将 test_time 追加到基类的日期时间处理列表中，以便统一渲染 datetime-local 组件
    DATETIME_FIELDS = BaseProcedureForm.DATETIME_FIELDS + ['test_time']

    class Meta:
        model = CVNSynthesis
        fields = [
            'start_time', 'expected_time', 'end_time', 'kettle',
            'raw_dcb', 'recycled_dcb', 'raw_nacn', 'raw_tbab', 'raw_alkali',
            'cvn_syn_crude_weight', 'remarks',
            'test_time', 'content_cvn', 'content_dcb', 'content_adn',
            'recovered_dcb_amount', 'waste_batches'
        ]

    def clean(self):

        cleaned_data = super().clean()
        action = self.action_type
        if action == 'finish_production':
            # cvn_syn工艺强制校验检测时间 (解决 test_time 允许留空问题)
            if 'test_time' in self.fields and not cleaned_data.get('test_time'):
                self.add_error('test_time', "确认完工必须录入质检/检测时间。")