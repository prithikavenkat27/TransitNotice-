/**
 * TransitNotice - Dashboard Charts & Visualization Engine
 * Connects to /api/dashboard-stats and renders Chart.js visualizations
 */

document.addEventListener('DOMContentLoaded', () => {
    initDashboardCharts();
});

async function initDashboardCharts() {
    const typeCanvas = document.getElementById('advisoryTypeChart');
    const statusCanvas = document.getElementById('statusChart');

    if (!typeCanvas || !statusCanvas) return;

    try {
        const response = await fetch('/api/dashboard-stats');
        const stats = await response.json();

        // 1. Advisory Type Breakdown Chart (Doughnut)
        const typeCtx = typeCanvas.getContext('2d');
        const typeColorMap = {
            'Diversion': '#f59e0b',
            'Delay': '#eab308',
            'Maintenance': '#0284c7',
            'Cancellation': '#ef4444',
            'Special Service': '#8b5cf6'
        };

        const typeColors = stats.types.labels.map(lbl => typeColorMap[lbl] || '#64748b');

        new Chart(typeCtx, {
            type: 'doughnut',
            data: {
                labels: stats.types.labels,
                datasets: [{
                    data: stats.types.data,
                    backgroundColor: typeColors,
                    borderWidth: 2,
                    borderColor: '#ffffff',
                    hoverOffset: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            boxWidth: 14,
                            padding: 12,
                            font: { family: "'Inter', sans-serif", size: 12 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) {
                                const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                                const val = ctx.raw;
                                const pct = Math.round((val / total) * 100);
                                return ` ${ctx.label}: ${val} notices (${pct}%)`;
                            }
                        }
                    }
                },
                cutout: '68%'
            }
        });

        // 2. Notice Status Distribution Chart (Bar)
        const statusCtx = statusCanvas.getContext('2d');
        const statusColorMap = {
            'Active': '#10b981',
            'Revised': '#8b5cf6',
            'Expired': '#64748b',
            'Cancelled': '#ef4444'
        };
        const statusColors = stats.statuses.labels.map(lbl => statusColorMap[lbl] || '#0284c7');

        new Chart(statusCtx, {
            type: 'bar',
            data: {
                labels: stats.statuses.labels,
                datasets: [{
                    label: 'Announcement Count',
                    data: stats.statuses.data,
                    backgroundColor: statusColors,
                    borderRadius: 6,
                    maxBarThickness: 45
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(ctx) {
                                return ` Status Count: ${ctx.raw} notices`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: { stepSize: 1, font: { family: "'JetBrains Mono', monospace" } },
                        grid: { color: '#f1f5f9' }
                    },
                    x: {
                        ticks: { font: { family: "'Inter', sans-serif", weight: '600' } },
                        grid: { display: false }
                    }
                }
            }
        });

    } catch (error) {
        console.error('Failed to load dashboard chart metrics:', error);
    }
}
