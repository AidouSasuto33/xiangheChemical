/**
 * static/js/production/partials/_batch_source_input.js
 * 通用多批次投入选择器组件 (UI & 数据广播引擎)
 * * 职责：
 * 1. 动态维护批次投入表格的增删改。
 * 2. 从隐藏标签中读取可用批次 JSON 和前置质检字段配置。
 * 3. 动态渲染 Datalist（去重）。
 * 4. 动态渲染当前行已选批次的“徽章信息”(余量、组份含量)。
 * 5. 计算总投入重量。
 * 6. 向全局抛出 `BatchDataChanged` 事件。
 */

document.addEventListener('DOMContentLoaded', function () {
    const tableBody = document.getElementById('batchSourceBody');
    const addBtn = document.getElementById('addBatchRowBtn');
    const template = document.getElementById('batchSourceRowTemplate');
    const totalWeightSpan = document.getElementById('totalInputWeight');

    // ==========================================
    // 1. 动态解析后端传来的 JSON 数据与展示配置
    // ==========================================
    let availableSources = [];
    let sourceQcInfo = []; // 动态展示的质检字段配置, 来自全局 BOM

    try {
        const jsonDataStr = document.getElementById('available-sources-data').textContent.trim();
        if (jsonDataStr) availableSources = JSON.parse(jsonDataStr);

        const qcInfoStr = document.getElementById('config-source-qc-info').textContent.trim();
        if (qcInfoStr) sourceQcInfo = JSON.parse(qcInfoStr);
    } catch (e) {
        console.error("解析可用批次或 QC 配置 JSON 失败", e);
    }

    // 动态创建 Datalist
    const dataList = document.createElement('datalist');
    dataList.id = 'availableBatches';
    document.body.appendChild(dataList);

    /**
     * 核心逻辑：动态组装 Datalist 的 Option 文本 (纯数据驱动)
     */
    function populateDatalist() {
        dataList.innerHTML = '';
        const selectedBatches = new Set();
        document.querySelectorAll('.batch-input').forEach(input => {
            const val = input.value.trim();
            if (val) selectedBatches.add(val);
        });

        availableSources.forEach(source => {
            if (!selectedBatches.has(source.batch_no)) {
                const option = document.createElement('option');
                option.value = source.batch_no;

                // --- 通用、动态组装质检信息展示文本 ---
                let extraInfo = "";
                sourceQcInfo.forEach(info => {
                    if (source[info.field] !== undefined && source[info.field] !== 0) {
                        // 这里的 info.name 就是来自 BOM 的文本，例如 "CVN含量%"
                        extraInfo += ` | ${info.name}: ${source[info.field]}%`;
                    }
                });

                option.text = `余量: ${source.remaining_weight}kg${extraInfo}`;
                dataList.appendChild(option);
            }
        });
    }

    // 初始化 Datalist
    populateDatalist();

    // ==========================================
    // 2. 数据处理与广播引擎 (Event Driven)
    // ==========================================
    function processAndBroadcastData() {
        let total = 0;
        const selectedBatchesData = [];

        // 1. 计算总重量
        document.querySelectorAll('#batchSourceBody tr').forEach(row => {
            const batchNo = row.querySelector('.batch-input')?.value;
            const weightInput = row.querySelector('.use-weight-input');
            const weight = parseFloat(weightInput?.value);

            if (!isNaN(weight) && weight > 0) {
                total += weight;
            }

            // 2. 收集有效批次数据用于广播
            if (batchNo && weight > 0) {
                const source = availableSources.find(s => s.batch_no === batchNo);
                if (source) {
                    selectedBatchesData.push({
                        batch_no: batchNo,
                        weight: weight,
                        data: source // 扔出整个批次数据字典
                    });
                }
            }
        });

        // 渲染 UI 总重量
        if (totalWeightSpan) totalWeightSpan.textContent = total.toFixed(2);

        // 渲染主表单的投入总重量字段
        const totalWeightFieldId = document.getElementById('config-total-weight-field')?.value;
        if (totalWeightFieldId) {
            const dryWeightDisplay = document.getElementById(totalWeightFieldId) || document.querySelector(`[name="${totalWeightFieldId}"]`);
            if (dryWeightDisplay) dryWeightDisplay.value = total.toFixed(1);
        }

        // 核心：抛出全局事件，让外挂计算器接管数学计算
        document.dispatchEvent(new CustomEvent('BatchDataChanged', { detail: selectedBatchesData }));
    }

    // ==========================================
    // 3. 核心计算与 UI 联动逻辑 (含徽章恢复)
    // ==========================================
    function handleBatchSelection(inputElement) {
        const batchNo = inputElement.value.trim();
        const row = inputElement.closest('tr');
        const weightInput = row.querySelector('.use-weight-input');
        const infoDiv = row.querySelector('.batch-info-container'); // 这是存放徽章的容器

        if (!batchNo) {
            infoDiv.innerHTML = '';
            processAndBroadcastData();
            populateDatalist();
            return;
        }

        // 防重复校验
        let isDuplicate = false;
        document.querySelectorAll('.batch-input').forEach(input => {
            if (input !== inputElement && input.value.trim() === batchNo) isDuplicate = true;
        });

        if (isDuplicate) {
            if (window.showGlobalError) {
                window.showGlobalError(`批号 [${batchNo}] 已在其他行中被选择！`);
            } else {
                alert('该批次已被选择！');
            }
            inputElement.value = '';
            infoDiv.innerHTML = '';
            processAndBroadcastData();
            return;
        }

        // ==========================================
        // *** 恢复徽章渲染：通用、数据驱动 ***
        // ==========================================
        const source = availableSources.find(s => s.batch_no === batchNo);
        if (source) {
            // 如果重量为空，默认填入该批次的全部余量
            if (!weightInput.value || parseFloat(weightInput.value) === 0) {
                weightInput.value = source.remaining_weight;
            }

            // 1. 固定徽章：可用余量
            let badgeHtml = `<span class="badge bg-success bg-opacity-10 text-success border border-success me-1">余: ${source.remaining_weight}kg</span>`;

            // 2. 动态徽章：遍历 BOM 配置，渲染各组份含量
            if (sourceQcInfo.length > 0) {
                let qcHtml = sourceQcInfo.map(info => {
                    // 这里我们将 BOM 名字里的 '%' 去掉，使 UI 更简洁
                    const displayName = info.name.replace('%', '').replace('含量', '');
                    const val = (source[info.field] || 0).toFixed(2);
                    return `${displayName} <strong class="text-dark">${val}%</strong>`;
                }).join(' | ');

                if (qcHtml) {
                    badgeHtml += `<span class="text-muted small">${qcHtml}</span>`;
                }
            }

            // 将徽章注入 DOM
            infoDiv.innerHTML = badgeHtml;
        } else {
            infoDiv.innerHTML = ''; // 如果找不到批次，清空信息
        }

        processAndBroadcastData();
        populateDatalist();
    }

    // ==========================================
    // 4. 基础表单事件绑定
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
            // 应对 autocomplete 选择的情况
            batchInput.addEventListener('input', (e) => {
                if(e.inputType === 'insertReplacementText' || !e.inputType) {
                    handleBatchSelection(batchInput)
                }
            });
        }
        if (weightInput) {
            weightInput.addEventListener('input', () => {
                processAndBroadcastData();
            });
        }
        if (removeBtn) {
            removeBtn.addEventListener('click', function () {
                if (tableBody.children.length <= 1) {
                    window.showGlobalError ? window.showGlobalError('至少需要保留一条投入明细！') : alert('至少保留一条！');
                    return;
                }
                row.remove();
                processAndBroadcastData();
                updateDeleteButtonsState();
                populateDatalist();
            });
        }
    }

    // ==========================================
    // 5. 初始化执行
    // ==========================================
    if (tableBody) {
        tableBody.querySelectorAll('tr').forEach(row => {
            bindRowEvents(row);
            const batchInput = row.querySelector('.batch-input');
            // 如果是编辑回显，手动触发一次徽章和数据计算
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

        if (tableBody.children.length === 0) {
            addBtn.click();
            const firstBatchInput = tableBody.querySelector('.batch-input');
            if (firstBatchInput) firstBatchInput.focus();
        }
    }
});