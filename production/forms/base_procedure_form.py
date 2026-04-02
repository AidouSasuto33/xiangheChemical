# production/forms/base_procedure_form.py
import json
from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.db import transaction
# 引入项目内部模型
from core.constants import KettleState
from production.models.kettle import Kettle
# 引入项目验证工具函数
from production.utils.qc_utils import validate_qc_sum_100
from production.utils.output_validator import validate_output_balance
from xiangheChemical.utils.time_utils import is_time_sequence_valid
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

    # --- 动态投入及多批次物料配置 (精馏及后续工艺使用) ---
    HAS_DYNAMIC_INPUTS = False  # 是否需要处理前置投入批次
    SOURCE_BATCH_MODEL = None  # 原料来源 Model (例如: CVNSynthesis)
    INPUT_RELATION_MODEL = None  # 投入明细关系 Model (例如: CVNDistillationInput)
    INPUT_RELATION_FK_NAME = None  # 关系表中指向当前主表的 ForeignKey 名称 (例如: 'distillation')
    TOTAL_INPUT_WEIGHT_FIELD = None  # 主表中用于汇总总投入重量的字段名 (例如: 'input_total_cvn_weight')

    # 新增：用于前端动态质检计算引擎的映射字典，基类默认为空，子类覆盖
    # 格式例如: {'pre_content_cvn': 'content_cvn'}
    QC_SOURCE_MAP = {}

    # --- 全局防篡改字段配置 ---
    READONLY_FIELDS = []  # 无论什么状态，始终由系统计算并锁死无法篡改的字段

    def __init__(self, *args, **kwargs):
        self.action_type = kwargs.pop('action_type', None)
        super().__init__(*args, **kwargs)

        # 将映射字典转为 JSON，挂载到实例上，供模板传递给前端计算引擎
        self.qc_source_map_json = json.dumps(self.QC_SOURCE_MAP)

        self._apply_readonly_fields()
        self._setup_datetime_widgets()
        self._setup_kettle_queryset()
        self._apply_bootstrap_styles()
        self._apply_status_locks()

    def _apply_readonly_fields(self):
        """强制锁定系统计算或流转过来的只读字段"""
        for field in self.READONLY_FIELDS:
            if field in self.fields:
                self.fields[field].disabled = True

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
        status = getattr(self.instance, 'status', 'new')
        if not status:
            status = 'new'

        if status == 'new':
            # Case 'new': 创建中，锁定所有产出信息，防止误填
            self._disable_fields(self.get_output_group())

        elif status == 'running':
            # Case 'running': 生产中，锁定开工投入信息，防止篡改
            self._disable_fields(self.get_input_group())

        elif status == 'completed' or status == 'abnormal':
            # Case 'completed': 结束生产/工单异常时锁定所有核心输入输出信息
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

    def _validate_input_time(self):
        start_time = self.cleaned_data.get('start_time')
        end_time = self.cleaned_data.get('end_time')
        test_time = self.cleaned_data.get('test_time')
        expected_time = self.cleaned_data.get('expected_time')
        status = getattr(self.instance, 'status', 'new')

        if status == 'running':
            # 规则 2: 完成时间 >= 开始时间 (严格大于)
            if not is_time_sequence_valid(start_time, end_time):
                self.add_error('end_time', "完成时间必须晚于开始时间。")

            # 规则 1: 送检时间 >= 完成时间
            if not is_time_sequence_valid(end_time, test_time):
                self.add_error('expected_time', "送检时间不能早于完成时间。")

        elif status == 'new':
            # 规则 3: 预计完成时间 >= 开始时间
            if not is_time_sequence_valid(start_time, expected_time):
                self.add_error('expected_time', "预计完成时间不能早于开始时间。")

    def clean(self):
        cleaned_data = super().clean()
        action = self.action_type

        # 先检查时间输入是否正确
        self._validate_input_time()

        # === 动态投入批次解析校验，并注入前置工艺产品投入总量到cleaned_data ===
        if self.HAS_DYNAMIC_INPUTS:
            cleaned_data = self._clean_dynamic_inputs(cleaned_data)

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

    def _clean_dynamic_inputs(self, cleaned_data):
        """解析并校验前端传来的多批次投入数组，剔除了具体的业务计算逻辑"""
        batch_nos = self.data.getlist('source_batch_no')
        use_weights = self.data.getlist('source_use_weight')

        if not batch_nos:
            raise ValidationError("请至少添加一条原料投入明细。")

        parsed_inputs = []
        total_weight = 0.0
        seen_batches = set()

        for batch_no, weight_str in zip(batch_nos, use_weights):
            batch_no = batch_no.strip()
            if not batch_no:
                continue

            # 1. 重量格式校验
            try:
                weight = float(weight_str)
            except (ValueError, TypeError):
                raise ValidationError(f"批号 [{batch_no}] 的重量格式不正确。")
            if weight <= 0:
                raise ValidationError(f"批号 [{batch_no}] 的投入重量必须大于 0。")

            # 2. 重复校验
            if batch_no in seen_batches:
                raise ValidationError(f"批号 [{batch_no}] 被重复添加，请合并重量后录入。")
            seen_batches.add(batch_no)

            # 3. 数据库真实性校验
            try:
                source_batch = self.SOURCE_BATCH_MODEL.objects.get(batch_no=batch_no)
            except self.SOURCE_BATCH_MODEL.DoesNotExist:
                raise ValidationError(f"系统内未找到原料批号：[{batch_no}]，请检查拼写。")

            parsed_inputs.append({
                'source_batch': source_batch,
                'use_weight': weight
            })
            total_weight += weight

        if not parsed_inputs:
            raise ValidationError("请添加有效的原料投入明细。")

        # 将干净数据暂存在 Form 实例中，供 save() 和子类的 clean() 业务逻辑使用
        self.parsed_inputs = parsed_inputs

        # 自动计算并覆盖主表的投入总重量
        if self.TOTAL_INPUT_WEIGHT_FIELD:
            if hasattr(self.instance, self.TOTAL_INPUT_WEIGHT_FIELD):
                setattr(self.instance, self.TOTAL_INPUT_WEIGHT_FIELD, total_weight)
            # 注入到 cleaned_data (供后续 validate_output_balance 使用)
            self.cleaned_data[self.TOTAL_INPUT_WEIGHT_FIELD] = total_weight

        # 2. 【核心安全增强】：基于 QC_SOURCE_MAP 执行通用后端加权计算
        if self.QC_SOURCE_MAP and total_weight > 0:
            for target_f, source_f in self.QC_SOURCE_MAP.items():
                # 算式：Σ (源批次含量 * 该批次投入重量) / 总投入重量
                weighted_sum = sum(
                    (getattr(item['source_batch'], source_f, 0) or 0) * item['use_weight']
                    for item in self.parsed_inputs
                )
                avg_val = weighted_sum / total_weight
                # 强制注入 instance 和 cleaned_data
                # 哪怕用户在前端用 F12 修改了值，这里也会根据原始数据重新覆盖
                if hasattr(self.instance, target_f):
                    setattr(self.instance, target_f, round(avg_val, 2))
                self.cleaned_data[target_f] = round(avg_val, 2)

        return cleaned_data

    def save(self, commit=True):
        """拦截默认的 save，利用事务确保主表与投入子表的一致性"""
        instance = super().save(commit=False)

        if commit:
            with transaction.atomic():
                instance.save()
                if self.HAS_DYNAMIC_INPUTS:
                    self._save_inputs(instance)
        return instance

    def _save_inputs(self, instance):
        """批量创建投入子表记录，并打上质量快照"""
        if hasattr(self, 'parsed_inputs') and self.INPUT_RELATION_MODEL:
            # 清理旧数据 (应对草稿多次保存的场景)
            instance.inputs.all().delete()

            new_inputs = []
            for item in self.parsed_inputs:
                source = item['source_batch']

                # 构建创建子表所需的基础 kwargs
                kwargs = {
                    self.INPUT_RELATION_FK_NAME: instance,
                    'source_batch': source,
                    'use_weight': item['use_weight'],
                }

                new_inputs.append(self.INPUT_RELATION_MODEL(**kwargs))

            self.INPUT_RELATION_MODEL.objects.bulk_create(new_inputs)