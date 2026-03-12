from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from production.models.cvn_distillation import CVNDistillation, CVNDistillationInput
from production.models.cvn_synthesis import CVNSynthesis


class CVNDistillationForm(forms.ModelForm):


    def __init__(self, *args, **kwargs):
        # 提取从 View 传入的 action_type
        self.action_type = kwargs.pop('action_type', None)
        super().__init__(*args, **kwargs)

        # === 1. Widget 显式配置 ===
        self.fields['start_time'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'})
        self.fields['expected_time'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'})
        self.fields['end_time'].widget = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local', 'class': 'form-control'})

        # === 2. 定义字段分组 ===
        input_group = ['start_time', 'expected_time', 'kettle']
        output_group = [
            'end_time', 'output_weight',
            'output_cvn_content', 'output_dcb_content', 'output_adn_content',
            'residue_weight'
        ]
        status = self.instance.status if self.instance else 'new'

        # === 3. 状态机 UI 锁定逻辑 ===
        # 3.1 无论什么状态，精前组份始终由系统计算，禁止人工篡改
        readonly_fields = ['pre_cvn_content', 'pre_dcb_content', 'pre_adn_content']
        for field in readonly_fields:
            if field in self.fields:
                # 抛弃 CSS 样式的干预，使用 Django 原生的后端防篡改锁
                self.fields[field].disabled = True

        # 3.2 动态流转锁定
        if status == 'new':
            # 创建中：锁定产出信息，防止误填
            for field in output_group:
                if field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].required = False

        elif status == 'running':
            # 生产中：锁定开工投入信息，防止修改
            for field in input_group:
                if field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].required = True

        elif status == 'completed':
            # 结束生产：锁定所有核心输入输出信息
            for field in input_group + output_group:
                if field in self.fields:
                    self.fields[field].disabled = True
                    self.fields[field].required = True

    def clean_output_weight(self):
        weight = self.cleaned_data.get('output_weight')
        # 如果是“确认完工”动作，必须填写精品重量
        if self.action_type == 'finish_production':
            if not weight or weight <= 0:
                raise ValidationError("确认完工时，必须填写大于 0 的精品重量。")
        return weight

    def clean_residue_weight(self):
        weight = self.cleaned_data.get('residue_weight')
        # 如果是“确认完工”动作，必须填写釜残重量（允许为 0，但不能不填）
        if self.action_type == 'finish_production':
            if weight is None or weight < 0:
                raise ValidationError("确认完工时，必须填写釜残重量（若无釜残请填 0）。")
        return weight

    def clean(self):
        cleaned_data = super().clean()

        # 如果工单已经投产或完工，不允许再修改投入来源，直接跳过数组解析
        if self.instance.status != 'new':
            return cleaned_data

        # --- 1. 结构性前置校验 (如设备、动作等基础信息) ---
        if self.action_type == 'start_production':
            if not cleaned_data.get('kettle'):
                self.add_error('kettle', "投产必须选择一个釜皿。")

        # 获取前端传来的动态数组 (由于这些字段不在 Meta.fields 中，必须从 self.data 直接提取)
        batch_nos = self.data.getlist('source_batch_no')
        use_weights = self.data.getlist('source_use_weight')

        # 在“创建订单”、“投产”或“保存草稿”时校验投入物料
        if self.action_type in ['create_plan', 'start_production', 'save_draft']:
            if not batch_nos:
                raise ValidationError("请至少添加一条粗正品投入明细。")


            parsed_inputs = []
            total_weight = 0.0
            seen_batches = set()

            for batch_no, weight_str in zip(batch_nos, use_weights):
                batch_no = batch_no.strip()
                if not batch_no:
                    continue  # 忽略空行

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
                    source_batch = CVNSynthesis.objects.get(batch_no=batch_no)
                except CVNSynthesis.DoesNotExist:
                    raise ValidationError(f"系统内未找到粗品批号：[{batch_no}]，请检查拼写。")

                parsed_inputs.append({
                    'source_batch': source_batch,
                    'use_weight': weight
                })
                total_weight += weight

            if not parsed_inputs:
                raise ValidationError("请添加有效的粗正品投入明细。")

            # 将解析和校验后的干净数据暂存在 Form 实例中，供 save() 方法使用
            self.parsed_inputs = parsed_inputs

            # 自动计算并覆盖主表的投入总重量
            self.instance.input_total_weight = total_weight

        return cleaned_data

    def save(self, commit=True):
        # 拦截默认的 save，先保存主表 (获取 ID)，再处理子表
        instance = super().save(commit=False)

        if commit:
            with transaction.atomic():
                instance.save()
                self._save_inputs(instance)

        return instance

    def _save_inputs(self, instance):
        # 只有在 clean 阶段成功解析了投入明细，才进行更新 (即只有 new 状态下才会执行)
        if hasattr(self, 'parsed_inputs'):
            # 清理旧数据 (应对草稿多次保存的场景)
            instance.inputs.all().delete()

            # 批量创建子表记录，并打上当前的质量快照
            new_inputs = []
            for item in self.parsed_inputs:
                source = item['source_batch']
                new_inputs.append(CVNDistillationInput(
                    distillation=instance,
                    source_batch=source,
                    use_weight=item['use_weight'],
                    snapshot_cvn=source.content_cvn,
                    snapshot_dcb=source.content_dcb,
                    snapshot_adn=source.content_adn,
                ))

            CVNDistillationInput.objects.bulk_create(new_inputs)

    class Meta:
        model = CVNDistillation
        fields = [
            'start_time', 'expected_time', 'end_time', 'kettle',
            'pre_cvn_content', 'pre_dcb_content', 'pre_adn_content',
            'output_weight', 'output_cvn_content', 'output_dcb_content', 'output_adn_content',
            'residue_weight',
        ]