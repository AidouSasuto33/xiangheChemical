# production/forms/base_procedure_form.py

from django import forms
from django.db.models import Q
from production.models.kettle import Kettle
from core.constants import KettleState
from production.utils.bom_utils import get_procedure_bom_info

# 1. 顶部引入验证工具
from production.utils.qc_utils import validate_qc_sum_100
from production.utils.output_validator import validate_output_balance


class BaseProcedureForm(forms.ModelForm):
    """
    生产工序基础 Form 基类
    封装通用的 Form 链路逻辑，包括：动作类型解析、UI组件设置、状态机字段锁定、釜皿过滤及基础校验。
    """

    # --- 子类必须覆盖的类属性 ---
    PROCEDURE_KEY = None  # 例如: 'cvn_synthesis'
    MAIN_OUTPUT_FIELD = None  # 例如: 'cvn_syn_crude_weight'
    INPUT_GROUP = []
    OUTPUT_GROUP = []

    DATETIME_FIELDS = ['start_time', 'expected_time', 'end_time']

    def __init__(self, *args, **kwargs):
        self.action_type = kwargs.pop('action_type', None)
        super().__init__(*args, **kwargs)

        # 动态获取子类定义的 procedure_key，避免在基类中为 None 时引发报错
        self._setup_datetime_widgets()
        self._setup_kettle_queryset()
        self._apply_bootstrap_styles()
        self._apply_status_locks()

    def _setup_datetime_widgets(self):
        """统一配置日期时间组件"""
        for field_name in self.DATETIME_FIELDS:
            if field_name in self.fields:
                self.fields[field_name].widget = forms.DateTimeInput(
                    format='%Y-%m-%dT%H:%M',
                    attrs={'type': 'datetime-local'}
                )

    def _setup_kettle_queryset(self):
        """釜皿过滤：只显示空闲的、待清洗的，或者是当前工单已经占用的（用于编辑回显）"""
        if 'kettle' in self.fields:
            current_kettle_id = self.instance.kettle_id if self.instance and self.instance.pk else None

            kettle_qs = Kettle.objects.filter(
                Q(status=KettleState.IDLE) |
                Q(status=KettleState.CLEANING) |
                Q(id=current_kettle_id)
            )
            self.fields['kettle'].queryset = kettle_qs

    def _apply_bootstrap_styles(self):
        """统一添加 Bootstrap form-control 样式"""
        for field_name, field in self.fields.items():
            existing_class = field.widget.attrs.get('class', '')
            if 'form-control' not in existing_class:
                field.widget.attrs['class'] = f"{existing_class} form-control".strip()

    def _apply_status_locks(self):
        """基于当前实例状态，执行字段的只读锁定逻辑"""
        # 兼容处理：确保实例有 status 属性
        status = getattr(self.instance, 'status', 'new')
        if not status:
            status = 'new'

        if status == 'new':
            # Case 'new': 创建中，锁定所有产出信息，防止误填
            self._disable_fields(self.get_output_group())

        elif status == 'running':
            # Case 'running': 生产中，锁定开工投入信息，防止篡改
            self._disable_fields(self.get_input_group())

        elif status == 'completed':
            # Case 'completed': 结束生产，锁定所有核心输入输出信息
            self._disable_fields(self.get_input_group() + self.get_output_group())

    def get_input_group(self):
        return self.INPUT_GROUP

    def get_output_group(self):
        return self.OUTPUT_GROUP

    def _disable_fields(self, field_list):
        """将指定列表中的字段设置为禁用并取消必填"""
        for field in field_list:
            if field in self.fields:
                self.fields[field].disabled = True
                self.fields[field].required = False

    def clean(self):
        cleaned_data = super().clean()
        action = self.action_type

        # === 1. 投产通用的结构性前置校验 ===
        if self.action_type == 'start_production':
            if 'kettle' in self.fields and not cleaned_data.get('kettle'):
                self.add_error('kettle', "投产必须选择一个釜皿。")

        # === 2. 完工动作校验 (Finish Validation) ===
        elif action == 'finish_production':
            # 动态获取主产物重量字段进行校验
            if self.MAIN_OUTPUT_FIELD and self.MAIN_OUTPUT_FIELD in self.fields:
                crude = cleaned_data.get(self.MAIN_OUTPUT_FIELD)
                if not crude or crude <= 0:
                    self.add_error(self.MAIN_OUTPUT_FIELD, "完工录入必须填写有效的产出重量。")

            # 2.2 强制校验结束时间
            if 'end_time' in self.fields and not cleaned_data.get('end_time'):
                self.add_error('end_time', "确认完工必须录入实际结束时间。")


            # 确保 procedure_key 存在时才进行组件计算与校验
            if self.PROCEDURE_KEY:
                # === 1. 质检百分比校验 ===
                is_qc_valid, qc_msg = validate_qc_sum_100(self.PROCEDURE_KEY, cleaned_data)
                if not is_qc_valid:
                    self.add_error(None, qc_msg)

                # === 2. 投入产出平衡校验 ===
                is_bal_valid, bal_msg = validate_output_balance(self.PROCEDURE_KEY, cleaned_data)
                if not is_bal_valid:
                    self.add_error(None, bal_msg)

        return cleaned_data