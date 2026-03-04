    document.addEventListener('DOMContentLoaded', function () {
        const tableBody = document.getElementById('batchSourceBody');
        const addBtn = document.getElementById('addBatchRowBtn');
        const template = document.getElementById('batchSourceRowTemplate');
        const totalWeightSpan = document.getElementById('totalInputWeight');

        // ==========================================
        // 1. 解析后端传来的 JSON 数据并生成 Datalist
        // ==========================================
        let availableSources = [];
        try {
            const jsonDataStr = document.getElementById('available-sources-data').textContent.trim();
            if (jsonDataStr) {
                availableSources = JSON.parse(jsonDataStr);
            }
        } catch (e) {
            console.error("解析可用批次 JSON 失败", e);
        }

        // 动态创建 Datalist 挂载到 body 下
        const dataList = document.createElement('datalist');
        dataList.id = 'availableBatches';
        availableSources.forEach(source => {
            const option = document.createElement('option');
            option.value = source.batch_no;
            // 提示文本在部分浏览器中会显示在批号旁边
            option.text = `余量: ${source.remaining_weight}kg | CVN: ${source.cvn}%`;
            dataList.appendChild(option);
        });
        document.body.appendChild(dataList);

        // ==========================================
        // 2. 核心计算与 UI 联动逻辑
        // ==========================================
        function updateTotalWeight() {
            if (!totalWeightSpan) return;
            let total = 0;
            document.querySelectorAll('.use-weight-input').forEach(input => {
                const val = parseFloat(input.value);
                if (!isNaN(val) && val > 0) total += val;
            });
            totalWeightSpan.textContent = total.toFixed(1);
        }



        // 加权平均组份演算引擎
        function calculateSummary() {
            let totalWeight = 0, sumCvn = 0, sumDcb = 0, sumAdn = 0;

            document.querySelectorAll('#batchSourceBody tr').forEach(row => {
                const batchNo = row.querySelector('.batch-input')?.value;
                const weight = parseFloat(row.querySelector('.use-weight-input')?.value) || 0;

                if (batchNo && weight > 0) {
                    const source = availableSources.find(s => s.batch_no === batchNo);
                    if (source) {
                        totalWeight += weight;
                        sumCvn += weight * (source.cvn / 100);
                        sumDcb += weight * (source.dcb / 100);
                        sumAdn += weight * (source.adn / 100);
                    }
                }
            });

            // 将计算结果自动填入主表单的精前组份栏位中
            const cvnInput = document.querySelector('[name="pre_cvn_content"]');
            const dcbInput = document.querySelector('[name="pre_dcb_content"]');
            const adnInput = document.querySelector('[name="pre_adn_content"]');

            if (cvnInput) cvnInput.value = totalWeight > 0 ? ((sumCvn / totalWeight) * 100).toFixed(2) : '';
            if (dcbInput) dcbInput.value = totalWeight > 0 ? ((sumDcb / totalWeight) * 100).toFixed(2) : '';
            if (adnInput) adnInput.value = totalWeight > 0 ? ((sumAdn / totalWeight) * 100).toFixed(2) : '';
        }

               // 选项池更新引擎：动态剔除已被选中的批次
        function updateDatalistOptions() {
            const dataList = document.getElementById('availableBatches');
            if (!dataList) return;

            // 1. 收集当前所有行已经填写的批号
            const selectedBatches = new Set();
            document.querySelectorAll('.batch-input').forEach(input => {
                const val = input.value.trim();
                if (val) selectedBatches.add(val);
            });

            // 2. 清空现有的下拉池
            dataList.innerHTML = '';

            // 3. 重新放回未被选中的批次
            availableSources.forEach(source => {
                if (!selectedBatches.has(source.batch_no)) {
                    const option = document.createElement('option');
                    option.value = source.batch_no;
                    option.text = `余量: ${source.remaining_weight}kg | CVN: ${source.cvn}%`;
                    dataList.appendChild(option);
                }
            });
        }

        // 智能感应：处理批次选中事件 (增强版：含防重复校验)
        function handleBatchSelection(inputElement) {
            const batchNo = inputElement.value.trim();
            const row = inputElement.closest('tr');
            const weightInput = row.querySelector('.use-weight-input');
            const infoDiv = row.querySelector('.batch-info-container');

            // 1. 如果输入被清空，同步清空徽章并重新计算
            if (!batchNo) {
                infoDiv.innerHTML = '';
                updateTotalWeight();
                calculateSummary();
                return;
            }

            // 2. 🚨 核心防御：校验是否已经在其他行被选择
            let isDuplicate = false;
            document.querySelectorAll('.batch-input').forEach(input => {
                // 排除自己，只对比其他行
                if (input !== inputElement && input.value.trim() === batchNo) {
                    isDuplicate = true;
                }
            });

            if (isDuplicate) {
                if (window.showGlobalError) {
                    window.showGlobalError(`批号 [${batchNo}] 已在其他行中被选择！\n如果需要增加用量，请直接修改对应行的重量。`);
                } else {
                    alert('该批次已被选择！');
                }
                inputElement.value = ''; // 强行清空违规输入
                infoDiv.innerHTML = '';  // 清空徽章
                updateTotalWeight();
                calculateSummary();
                return; // 中断后续操作
            }

            // 3. 原有逻辑：渲染徽章与自动带入重量
            const source = availableSources.find(s => s.batch_no === batchNo);
            if (source) {
                // 如果当前重量为空或为 0，自动带入最大剩余重量
                if (!weightInput.value || parseFloat(weightInput.value) === 0) {
                    weightInput.value = source.remaining_weight;
                }

                // 渲染高颜值数据徽章
                infoDiv.innerHTML = `
                    <span class="badge bg-success bg-opacity-10 text-success border border-success me-1">余: ${source.remaining_weight}kg</span>
                    <span class="text-muted">CVN <strong class="text-dark">${source.cvn}%</strong> | DCB <strong class="text-dark">${source.dcb}%</strong> | ADN <strong class="text-dark">${source.adn}%</strong></span>
                `;
            } else {
                infoDiv.innerHTML = ''; // 找不到有效批次则清空
            }

            updateTotalWeight();
            calculateSummary();
            updateDatalistOptions();
        }

        // ==========================================
        // 3. 基础表单事件绑定
        // ==========================================
        function updateDeleteButtonsState() {
            const rows = tableBody.querySelectorAll('tr');
            const deleteBtns = tableBody.querySelectorAll('.remove-row-btn');
            if (rows.length <= 1) {
                deleteBtns.forEach(btn => { btn.disabled = true; btn.classList.add('opacity-50'); });
            } else {
                deleteBtns.forEach(btn => { btn.disabled = false; btn.classList.remove('opacity-50'); });
            }
        }

        function bindRowEvents(row) {
            const batchInput = row.querySelector('.batch-input');
            const weightInput = row.querySelector('.use-weight-input');
            const removeBtn = row.querySelector('.remove-row-btn');

            if (batchInput) {
                batchInput.addEventListener('change', () => handleBatchSelection(batchInput));
                // 解决某些浏览器 input 事件不触发的问题
                batchInput.addEventListener('input', () => handleBatchSelection(batchInput));
            }
            if (weightInput) {
                weightInput.addEventListener('input', () => {
                    updateTotalWeight();
                    calculateSummary();
                });
            }
            if (removeBtn) {
                removeBtn.addEventListener('click', function () {
                    if (tableBody.children.length <= 1) {
                        window.showGlobalError ? window.showGlobalError('至少需要保留一条投入明细！') : alert('至少保留一条！');
                        return;
                    }
                    row.remove();
                    updateTotalWeight();
                    calculateSummary();
                    updateDeleteButtonsState();
                });
            }
        }

        // ==========================================
        // 4. 初始化执行
        // ==========================================
        if (tableBody) {
            tableBody.querySelectorAll('tr').forEach(row => {
                bindRowEvents(row);
                // 对于回显的数据，主动触发一次解析，渲染徽章并计算总计
                const batchInput = row.querySelector('.batch-input');
                if (batchInput && batchInput.value) {
                    handleBatchSelection(batchInput);
                }
            });
            updateDeleteButtonsState();
        }

        if (addBtn && template) {
            addBtn.addEventListener('click', function () {
                const newRow = template.content.cloneNode(true).querySelector('tr');
                bindRowEvents(newRow);
                tableBody.appendChild(newRow);
                updateDeleteButtonsState();
            });

            // 全新工单默认加一行
            if (tableBody.children.length === 0) {
                addBtn.click();
                const firstBatchInput = tableBody.querySelector('.batch-input');
                if (firstBatchInput) firstBatchInput.focus(); // 自动聚焦
            }
        }
    });