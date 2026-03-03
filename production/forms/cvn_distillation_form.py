from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from production.models.cvn_distillation import CVNDistillation, CVNDistillationInput
from production.models.cvn_synthesis import CVNSynthesis


class CVNDistillationForm(forms.ModelForm):
    class Meta:
        model = CVNDistillation
        fields = [
            'kettle',
            'pre_cvn_content', 'pre_dcb_content', 'pre_adn_content',
            'output_weight', 'output_cvn_content', 'output_dcb_content', 'output_adn_content',
            'residue_weight',
        ]
        # widgets = {
        #     'note': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        #     'kettle': forms.Select(attrs={'class': 'form-select'}),
        # }

    def __init__(self, *args, **kwargs):
        # 提取从 View 传入的 action_type
        self.action_type = kwargs.pop('action_type', None)
        super().__init__(*args, **kwargs)

        # 1. UI 控制：精前组份始终为只读（由前端/后端自动计算或通过专门的化验单录入）
        readonly_fields = ['pre_cvn_content', 'pre_dcb_content', 'pre_adn_content']
        for field in readonly_fields:
            if field in self.fields:
                self.fields[field].widget.attrs['readonly'] = True
                self.fields[field].widget.attrs['class'] = 'form-control bg-light'

        # 2. 状态保护：如果不是新建状态，禁用釜皿选择
        if self.instance and self.instance.status != 'new':
            if 'kettle' in self.fields:
                self.fields['kettle'].widget.attrs['disabled'] = True

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

        # 获取前端传来的动态数组
        batch_nos = self.data.getlist('source_batch_no')
        use_weights = self.data.getlist('source_use_weight')

        # 仅在“投产”或“保存草稿”时校验投入物料
        if self.action_type in ['start_production', 'save_draft']:
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