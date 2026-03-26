/**
 * 湘和化工厂 MES - 智能图表渲染引擎 (Auto-Refresh Engine)
 * 职责：自动监听组件级参数变化、组装请求、智能适配折线/柱状/饼图
 */

const CHART_API_URL = '/production/charts/'; // ⚠️ 替换为真实的通用 API 路由

document.addEventListener('DOMContentLoaded', () => {
    const chartCards = document.querySelectorAll('.chart-card-container');

    // 1. 页面加载，全军出击，初始化所有卡片
    chartCards.forEach(card => refreshSingleChart(card));

    // 2. 窗口缩放，全员自适应
    window.addEventListener('resize', () => {
        chartCards.forEach(card => {
            const canvas = card.querySelector('.echart-canvas');
            if (canvas) {
                const myChart = echarts.getInstanceByDom(canvas);
                if (myChart) myChart.resize();
            }
        });
    });
});

/**
 * ==========================================
 * 全局事件监听 (Event Delegation)
 * ==========================================
 */

// 监听所有下拉框和开关的变化
document.addEventListener('change', function(e) {
    if (e.target.closest('.period-selector')) {
        const card = e.target.closest('.chart-card-container');
        if (card) refreshSingleChart(card);
    }
});

// 监听数字输入框 (带防抖处理，避免输入 "12" 时触发两次请求)
let debounceTimer;
document.addEventListener('input', function(e) {
    if (e.target.classList.contains('input-intervals')) {
        const card = e.target.closest('.chart-card-container');
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            if (card) refreshSingleChart(card);
        }, 500); // 用户停顿 0.5 秒后触发
    }
});

/**
 * ==========================================
 * 核心：单卡片刷新与渲染逻辑
 * ==========================================
 */
async function refreshSingleChart(cardElement) {
    const canvas = cardElement.querySelector('.echart-canvas');
    let myChart = echarts.getInstanceByDom(canvas) || echarts.init(canvas);

    // 开启加载动画
    myChart.showLoading({ text: '数据计算中...', color: '#0d6efd' });

    try {
        // --- 1. 提取静态配置 (Data Attributes) ---
        const { dataset, metricField, metricName, metricFunc, isStacked } = cardElement.dataset;

        // --- 2. 提取动态控制台配置 ---
        const chartType = cardElement.querySelector('.select-chart-type').value;
        const unit = cardElement.querySelector('.select-unit').value;
        const intervals = cardElement.querySelector('.input-intervals').value;

        // 提取对比开关状态
        const popCheck = cardElement.querySelector('.check-pop');
        const yoyCheck = cardElement.querySelector('.check-yoy');
        const isPop = popCheck ? popCheck.checked : false;
        const isYoy = yoyCheck ? yoyCheck.checked : false;

        // 确定对比模式 (优先级：同比 > 环比)
        let comparisonMode = null;
        if (isYoy) comparisonMode = 'TOP';
        else if (isPop) comparisonMode = 'POP';

        // --- 3. 组装网关 Payload ---
        const payload = {
            dataset: dataset,
            unit: unit,
            intervals: parseInt(intervals, 10) || 12,
            comparison_mode: comparisonMode,
            is_stacked: isStacked === 'true',
            metrics: [{
                key: metricField,
                name: metricName || '指标',
                func: metricFunc || 'SUM',
                field: metricField,
                type: chartType // 将前端动态选择的类型发给后端
            }]
        };

        // --- 4. 发起请求 ---
        const response = await fetch(CHART_API_URL, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        // --- 5. ECharts 智能渲染适配 ---
        if (result.code === 200) {
            const data = result.data.chart_data;
            const isPie = chartType === 'pie';

            // 动态处理图表配置
            const option = {
                tooltip: {
                    // 饼图的 tooltip 是按色块触发，走势图是按纵轴触发
                    trigger: isPie ? 'item' : 'axis',
                    axisPointer: isPie ? undefined : { type: 'shadow' }
                },
                legend: { bottom: 0 }, // 图例始终沉底

                // 饼图不需要直角坐标系 (Grid, xAxis, yAxis)
                grid: isPie ? undefined : { left: '3%', right: '4%', bottom: '15%', containLabel: true },
                xAxis: isPie ? undefined : {
                    type: 'category',
                    data: data.xAxis,
                    axisLabel: { interval: 'auto' }
                },
                yAxis: isPie ? undefined : {
                    type: 'value',
                    name: (metricName && metricName.includes('(')) ? metricName.split('(')[1].replace(')','') : ''
                },

                // 动态处理 Series
                series: data.series.map(s => {
                    // 覆盖类型以防万一
                    s.type = chartType;

                    // 💥 饼图转换黑科技：如果后端传回的是走势数组 [10, 20, 30]
                    // 我们把它自动拼装成饼图需要的对象数组 [{name: '03-01', value: 10}, ...]
                    if (isPie && Array.isArray(s.data) && typeof s.data[0] !== 'object') {
                        s.data = s.data.map((val, idx) => ({
                            name: data.xAxis[idx] || `阶段 ${idx+1}`,
                            value: val
                        }));
                        s.radius = ['40%', '70%']; // 漂亮的环形饼图样式
                        s.avoidLabelOverlap = true;
                    }
                    return s;
                })
            };

            myChart.hideLoading();
            myChart.setOption(option, true); // true 代表清除旧画布，完全重绘

            // 更新卡片底部的状态栏
            const summary = cardElement.querySelector('.summary-label');
            if (summary && result.data.summary_label) {
                summary.textContent = `当前展示截至: ${result.data.summary_label}`;
                summary.classList.remove('text-danger');
            }
        } else {
            throw new Error(result.error || '后端业务异常');
        }

    } catch (error) {
        myChart.hideLoading();
        console.error("图表刷新失败", error);
        const summary = cardElement.querySelector('.summary-label');
        if (summary) {
            summary.textContent = `加载异常: ${error.message}`;
            summary.classList.add('text-danger');
        }
    }
}

// 获取 Django CSRF Token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}