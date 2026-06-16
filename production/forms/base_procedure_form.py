# production/forms/base_procedure_form.py
import json
from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.db import transaction
# 引入项目内部模型
from core.constants import KettleState, ProcedureState, ProcedureAction
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
    QC_GROUP = []
    DATETIME_FIELDS = ['start_time', 'expected_time', 'end_time', 'test_time']

    # --- 动态投入及多批次物料配置 (精馏及后续工艺使用) ---
    HAS_DYNAMIC_INPUTS = False  # 是否需要处理前置投入批次
    SOURCE_BATCH_MODEL = None  # 原料来源 Model (例如: CVNSynthesis)
    INPUT_RELATION_MODEL = None  # 投入明细关系 Model (例如: CVNDistillationInput)
    INPUT_RELATION_FK_NAME = None  # 关系表中指向当前主表的 ForeignKey 名称 (例如: 'distillation')
    TOTAL_INPUT_WEIGHT_FIELD = None  # 主表中用于汇总总投入重量的字段名 (例如: 'input_total_cvn_weight')

    # 新增：用于前端动态质检计算引擎的映射字典，基类默认为空，子类覆盖
    # 格式例: {'pre_content_cvn': 'content_cvn'}
    QC_SOURCE_MAP = {}

    # --- 全局防篡改字段配置 ---
    READONLY_FIELDS = []  # 无论什么状态，始终由系统计算并锁死无法篡改的字段

    def __init__(self, *args, **kwargs):
        self.action_type = kwargs.pop('action_type', None)
        super().__init__(*args, **kwargs)

        # 将映射字典转为 JSON，挂载到实例上，供模板传递给前端计算引擎
        self.qc_source_map_json = json.dumps(self.QC_SOURCE_MAP)

        self._setup_datetime_widgets()
        self._setup_kettle_queryset()
        # 严格的执行顺序：基础样式 -> 绝对只读 -> 状态机锁定
        self._apply_bootstrap_styles()
        self._apply_readonly_fields()
        self._apply_status_locks()


    def _apply_readonly_fields(self):
        """全局绝对防篡改字段锁定"""
        for field_name in getattr(self, 'READONLY_FIELDS', []):
            if field_name in self.fields:
                self._lock_single_field(self.fields[field_name])

    def _lock_single_field(self, field):
        """
        原子化锁定工具：不仅赋予 readonly，还通过 CSS 切断鼠标事件，
        彻底规避 Django 中 disabled 导致的数据丢失陷阱。
        """
        field.widget.attrs['readonly'] = 'readonly'
        # pointer-events: none 是精髓，它能防住 select 框的下拉和 checkbox 的点击
        field.widget.attrs['style'] = field.widget.attrs.get('style', '') + '; pointer-events: none;'
        field.widget.attrs['class'] = field.widget.attrs.get('class', '') + ' bg-light text-muted'

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
        """
        基于工单状态机的分段式 UI 区域动态锁定
        设计约定：
        1. NEW 状态：工单排产投料阶段，仅开放 INPUT_GROUP，锁死产出与质检。
        2. RUNNING 状态：车间生产放料阶段，仅开放 OUTPUT_GROUP，锁死投料与质检。
        3. PENDING_QC 状态：化验室结果录入阶段，仅开放 QC_GROUP，锁死投料与产出。
        4. 其他归档/异常状态：全场锁死，单据定格。
        """
        # 获取当前工单的真实状态，新建单据无 PK 时默认作为 NEW 状态处理
        status = self.instance.status if self.instance and self.instance.pk else ProcedureState.NEW

        # 根据状态机动态计算当前阶段需要被“锁死”的字段集合
        fields_to_lock = []

        if status == ProcedureState.NEW:
            # 1. 新工单状态：可填写的只有 input_group，必须锁死产出区和质检区
            fields_to_lock = self.OUTPUT_GROUP + self.QC_GROUP

        elif status == ProcedureState.RUNNING:
            # 2. 生产中状态：仅可填写 output_group，必须锁死投料区和质检区
            fields_to_lock = self.INPUT_GROUP + self.QC_GROUP

        elif status == ProcedureState.PENDING_QC:
            # 3. 待质检状态：仅可填写 qc_group，必须锁死投料区和产出区
            fields_to_lock = self.INPUT_GROUP + self.OUTPUT_GROUP

        else:
            # 4. 处于已完成(COMPLETED)、已取消(CANCEL)、异常(ABNORMAL)等最终归档状态，全场锁死
            fields_to_lock = self.INPUT_GROUP + self.OUTPUT_GROUP + self.QC_GROUP

        # 遍历出的锁死清单，调起单字段原子锁定防线
        for field_name in fields_to_lock:
            if field_name in self.fields:
                self._lock_single_field(self.fields[field_name])

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
        action = getattr(self, 'action_type', cleaned_data.get('action'))

        # 先检查时间输入是否正确
        self._validate_input_time()

        # === 动态投入批次解析校验，并注入前置工艺产品投入总量到cleaned_data ===
        if self.HAS_DYNAMIC_INPUTS:
            cleaned_data = self._clean_dynamic_inputs(cleaned_data)

        # ==========================================
        # 1. 投产动作校验 (Start Validation)
        # ==========================================
        if action == ProcedureAction.START_PRODUCTION:
            if 'kettle' in self.fields and not cleaned_data.get('kettle'):
                self.add_error('kettle', "投产必须选择一个釜皿。")

        # ==========================================
        # 2. 完工动作校验 (Finish Validation)
        # -> 车间放料交接：只对重量和时间负责
        # ==========================================
        elif action == ProcedureAction.FINISH_PRODUCTION:
            # 2.1 动态获取主产物重量字段进行校验
            if self.MAIN_OUTPUT_FIELD and self.MAIN_OUTPUT_FIELD in self.fields:
                crude = cleaned_data.get(self.MAIN_OUTPUT_FIELD)
                if not crude or crude <= 0:
                    self.add_error(self.MAIN_OUTPUT_FIELD, "完工交接必须填写有效的产出重量。")

            # 2.2 强制校验结束时间
            if 'end_time' in self.fields and not cleaned_data.get('end_time'):
                self.add_error('end_time', "确认完工必须录入实际结束时间。")

            # 2.3 投入产出平衡校验 (纯物理重量计算，由车间主任对重量偏差负责)
            if self.PROCEDURE_KEY:
                is_bal_valid, bal_msg = validate_output_balance(self.PROCEDURE_KEY, cleaned_data)
                if not is_bal_valid:
                    self.add_error(None, bal_msg)

        # ==========================================
        # 3. 质检闭环动作校验 (QC Validation)
        # -> 化验室出单：只对成分指标负责
        # ==========================================
        elif action == ProcedureAction.SUBMIT_QC:
            # 3.1 确保化验员填满了所有质检必填项
            for qc_field in self.QC_GROUP:
                if qc_field in self.fields and cleaned_data.get(qc_field) is None:
                    self.add_error(qc_field, "闭环工单前，必须录入此质检指标。")

            # 3.2 质检百分比合法性校验 (如：各项含量相加是否等于/接近100%)
            if self.PROCEDURE_KEY:
                is_qc_valid, qc_msg = validate_qc_sum_100(self.PROCEDURE_KEY, cleaned_data)
                if not is_qc_valid:
                    self.add_error(None, qc_msg)

        return cleaned_data

    def _clean_dynamic_inputs(self, cleaned_data):
        """解析并校验前端传来的多批次投入数组，剔除了具体的业务计算逻辑"""
        batch_nos = self.data.getlist('source_batch_no')
        use_weights = self.data.getlist('source_use_weight')
        if not batch_nos:
            raise ValidationError("请至少添加一条原料投入明细。")

        parsed_inputs = []
        insufficient_errors = []
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

            # 【核心改动 2】：发现超领时绝不立刻 raise，而是塞进错误弹框池
            # 仅在new状态下进行检验，进入running时会消耗批次雨量。若在running->pending_qc也进行检查，一定报错批量不足。
            if self.instance.status=='new' and weight > source_batch.remaining_weight:
                insufficient_errors.append(
                    f"批号 [{batch_no}] 结余不足 (需 {weight}kg, 存 {source_batch.remaining_weight}kg)"
                )

            parsed_inputs.append({
                'source_batch': source_batch,
                'use_weight': weight
            })
            total_weight += weight

        if not parsed_inputs:
            raise ValidationError("请添加有效的原料投入明细。")
        if insufficient_errors:
            # Django 的 ValidationError 完美支持传入一个错误列表
            raise ValidationError(insufficient_errors)

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
                    self._save_batch_source_inputs(instance)
        return instance

    def _save_batch_source_inputs(self, instance):
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

    def save_inputs(self, instance=None):
        """
        供外部 View 显式调用的子表独立落库方法。
        配合 commit=False 使用，利用现有主表 PK 擦除并重建投入明细，规避主表重复保存。
        """
        target_instance = instance or self.instance
        if self.HAS_DYNAMIC_INPUTS:
            self._save_batch_source_inputs(target_instance)