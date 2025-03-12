// chart.js 常用配置和工具函数

// 为Chart.js设置暗色主题
Chart.defaults.color = '#B0B0B0';
Chart.defaults.borderColor = '#333333';

// 为图表设置暗色主题
const darkThemeColors = {
    primary: '#3F51B5',
    primaryLight: '#7986CB',
    accent: '#FF4081',
    success: '#4CAF50',
    warning: '#FFC107',
    danger: '#F44336',
    info: '#2196F3',
    background: '#121212',
    surface: '#1E1E1E',
    surface2: '#2D2D2D',
    textPrimary: '#FFFFFF',
    textSecondary: '#B0B0B0',
    border: '#333333'
};

// 通用图表配置
function getDefaultChartOptions(title) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: {
                    color: darkThemeColors.textPrimary,
                    font: {
                        family: "'Roboto', sans-serif",
                        size: 12
                    }
                }
            },
            title: {
                display: !!title,
                text: title || '',
                color: darkThemeColors.textPrimary,
                font: {
                    family: "'Roboto', sans-serif",
                    size: 16,
                    weight: 'bold'
                }
            },
            tooltip: {
                backgroundColor: darkThemeColors.surface2,
                titleColor: darkThemeColors.textPrimary,
                bodyColor: darkThemeColors.textSecondary,
                borderColor: darkThemeColors.border,
                borderWidth: 1,
                cornerRadius: 4,
                displayColors: true,
                padding: 10,
                titleFont: {
                    family: "'Roboto', sans-serif",
                    size: 14,
                    weight: 'bold'
                },
                bodyFont: {
                    family: "'Roboto', sans-serif",
                    size: 13
                }
            }
        },
        scales: {
            x: {
                grid: {
                    color: 'rgba(255, 255, 255, 0.1)'
                },
                ticks: {
                    color: darkThemeColors.textSecondary
                }
            },
            y: {
                grid: {
                    color: 'rgba(255, 255, 255, 0.1)'
                },
                ticks: {
                    color: darkThemeColors.textSecondary
                }
            }
        },
        animation: {
            duration: 1000,
            easing: 'easeOutQuart'
        }
    };
}

// 颜色配置
const chartColors = {
    primary: 'rgba(54, 162, 235, 0.7)',
    secondary: 'rgba(153, 102, 255, 0.7)',
    success: 'rgba(75, 192, 192, 0.7)',
    danger: 'rgba(255, 99, 132, 0.7)',
    warning: 'rgba(255, 159, 64, 0.7)',
    info: 'rgba(201, 203, 207, 0.7)'
};

// 格式化日期
function formatDate(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit'
    });
}

// 格式化价格
function formatPrice(price) {
    return '$' + parseFloat(price).toFixed(2);
}

// 计算数据的平均值
function calculateAverage(data) {
    if (!data || data.length === 0) return 0;
    const sum = data.reduce((a, b) => a + b, 0);
    return sum / data.length;
}

// 格式化大数字
function formatLargeNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num;
}

// 创建价格变动图表
function createPriceChangeChart(chartId, labels, data, options = {}) {
    const ctx = document.getElementById(chartId).getContext('2d');
    return new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '价格',
                data: data,
                backgroundColor: chartColors.primary,
                borderColor: chartColors.primary.replace('0.7', '1'),
                borderWidth: 2,
                fill: false,
                tension: 0.4
            }]
        },
        options: Object.assign({}, getDefaultChartOptions(), options)
    });
}

// 创建柱状图
function createBarChart(chartId, labels, data, label = '数量', color = 'primary', options = {}) {
    const ctx = document.getElementById(chartId).getContext('2d');
    return new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: label,
                data: data,
                backgroundColor: chartColors[color],
                borderColor: chartColors[color].replace('0.7', '1'),
                borderWidth: 1
            }]
        },
        options: Object.assign({}, getDefaultChartOptions(), options)
    });
}