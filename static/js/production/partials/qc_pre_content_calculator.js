/**
 * static/js/production/partials/qc_pre_content_calculator.js
 * 前置质量组份加权计算引擎 (Plug-in Calculator)
 * * 职责：
 * 1. 监听多批次选择器发出的 `BatchDataChanged` 事件。
 * 2. 读取后端注入的 `config-qc-map` 映射规则。
 * 3. 执行加权平均计算，并将结果自动填入对应的 Input 框。
 */

document.addEventListener('DOMContentLoaded', function () {
    // 1. 获取映射规则配置 (由后端 Form 注入)
    const mapInput = document.getElementById('config-qc-map');
    if (!mapInput || !mapInput.value || mapInput.value === '{}') {
        console.log("QC Calculator: 未检测到有效的 QC_SOURCE_MAP，计算引擎休眠。");
        return;
    }

    let qcMap = {};
    try {
        qcMap = JSON.parse(mapInput.value);
    } catch (e) {
        console.error("QC Calculator: 解析 config-qc-map 失败", e);
        return;
    }

    // 2. 监听多批次数据变更事件
    document.addEventListener('BatchDataChanged', function (e) {
        const batches = e.detail; // 格式: [{ weight: 100, data: { content_cvn: 98, ... } }, ...]

        let totalWeight = 0;

        // 初始化目标字段的总累加值字典
        let sumMap = {};
        for (const targetName in qcMap) {
            sumMap[targetName] = 0;
        }

        // 3. 核心计算：遍历收集到的批次，执行加权累加
        batches.forEach(batch => {
            const w = parseFloat(batch.weight);
            if (isNaN(w) || w <= 0) return;

            totalWeight += w;

            for (const [targetName, sourceName] of Object.entries(qcMap)) {
                // 读取源含量，如果没有则默认为 0
                const val = parseFloat(batch.data[sourceName]) || 0;
                // 加权核心公式：重量 * 含量
                sumMap[targetName] += w * val;
            }
        });

        // 4. 计算加权平均并向页面 DOM 赋值
        for (const [targetName, sourceName] of Object.entries(qcMap)) {
            const inputNode = document.querySelector(`[name="${targetName}"]`);
            if (inputNode) {
                if (totalWeight > 0) {
                    const weightedAvg = sumMap[targetName] / totalWeight;
                    inputNode.value = weightedAvg.toFixed(2);
                } else {
                    inputNode.value = ''; // 如果总重量为 0，清空输入框
                }
            }
        }
    });
});