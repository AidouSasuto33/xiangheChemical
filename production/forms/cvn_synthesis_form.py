from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from production.models.cvn_synthesis import CVNSynthesis
from production.models.kettle import Kettle
from inventory.services import inventory_service
from core import constants

class CVNSynthesisForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        # 提取 View 传来的动作类型
        self.action_type = kwargs.pop('action_type', None)
        super().__init__(*args, **kwargs)

        # === 1. Widget Setup ===
        # Explicitly define widgets for start_time , expected_time, end_time , test_time
        self.fields['start_time'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'})
        self.fields['expected_time'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'})
        self.fields['end_time'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'})
        self.fields['test_time'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'})

        # === 2. Define Field Groups ===
        input_group = ['start_time', 'expected_time','kettle', 'raw_dcb', 'recycled_dcb', 'raw_nacn', 'raw_tbab', 'raw_alkali']
        output_group = ['end_time', 'test_time', 'cvn_syn_crude_weight', 'content_cvn', 'content_dcb', 'content_adn', 'recovered_dcb_amount', 'waste_batches']

        # === 3. Implement Status Locking Logic ===
        status = self.instance.status if self.instance.pk else 'new'

        if status == 'new':
            # Case 'new' (or None): Disable all fields in output_group.
            for field in output_group:
                if field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].required = False

        elif status == 'running':
            # Case 'running': Disable all fields in input_group.
            for field in input_group:
                if field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].required = False

        elif status == 'completed':
            # Case 'completed': Disable BOTH input_group and output_group.
            for field in input_group + output_group:
                if field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].required = False

        # Note: remarks (Step 4) should remain editable in all states.

        # === 4. Kettle Filtering ===
        # 逻辑：只显示空闲的，或者是当前工单已经占用的(用于编辑回显)
        current_kettle_id = self.instance.kettle_id if self.instance.pk else None
        
        # 构造查询：状态是idle OR to_clean OR id是当前id
        kettle_qs = Kettle.objects.filter(
            Q(status=constants.KettleState.IDLE) | Q(status=constants.KettleState.CLEANING) | Q(id=current_kettle_id)
        )
        self.fields['kettle'].queryset = kettle_qs

        # === 5. 统一添加样式 (Bootstrap Style) ===
        for field_name, field in self.fields.items():
            # 保留原有的 class (如果有)
            existing_class = field.widget.attrs.get('class', '')
            if 'form-control' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-control".strip()
            
            # 针对特定字段优化体验 (可选)
            if field_name in ['test_time']:
                field.widget.attrs['type'] = 'datetime-local'

    def clean(self):
        cleaned_data = super().clean()
        action = self.action_type
        
        # === 3. 投产动作校验 (Start Validation) ===
        if action == 'start_production':
            # 必须选择釜皿
            if not cleaned_data.get('kettle'):
                self.add_error('kettle', "投产必须选择一个釜皿")

        # === 4. 完工动作校验 (Finish Validation) ===
        elif action == 'finish_production':
            crude = cleaned_data.get('cvn_syn_crude_weight')
            if not crude or crude <= 0:
                self.add_error('cvn_syn_crude_weight', "完工录入必须填写有效的产出重量")

        return cleaned_data

    
    class Meta:
        model = CVNSynthesis
        fields = [
            'start_time', 'expected_time','end_time', 'kettle',
            'raw_dcb', 'recycled_dcb', 'raw_nacn', 'raw_tbab', 'raw_alkali',
            'cvn_syn_crude_weight', 'remarks',
            'test_time', 'content_cvn', 'content_dcb', 'content_adn',
            'recovered_dcb_amount', 'waste_batches'
        ]