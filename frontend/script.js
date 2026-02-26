// API Configuration
const API_BASE_URL = 'https://ai-sales-analytics.onrender.com/api';

// DOM Elements
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const fileInfo = document.getElementById('fileInfo');
const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const statusIndicator = document.getElementById('statusIndicator');
const statusDot = document.getElementById('statusDot');
const statusLoader = document.getElementById('statusLoader');
const statusText = document.getElementById('statusText');

// State
let selectedFile = null;
const productTrendCharts = {};

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    initThemeToggle();
    initGoTopButton();
    setupEventListeners();

    // Clear all backend data on every page load to avoid stale Gemini API calls
    try {
        await fetch(`${API_BASE_URL}/clear`, { method: 'POST' });
    } catch (e) {
        // Backend may not be up yet — that's fine
    }

    // Reset predictions state
    window._predictionsLoaded = false;
    _predictionsCache = null;

    checkBackendStatus();
    loadSampleFiles();
});

// Go to Top button (mobile)
function initGoTopButton() {
    const btn = document.getElementById('goTopBtn');
    if (!btn) return;
    window.addEventListener('scroll', () => {
        btn.classList.toggle('visible', window.scrollY > 300);
    }, { passive: true });
}

// Theme Toggle
function initThemeToggle() {
    const toggle = document.getElementById('themeToggle');
    const saved = localStorage.getItem('theme');
    if (saved === 'dark') {
        document.body.classList.add('dark-theme');
        toggle.checked = true;
    }
    toggle.addEventListener('change', () => {
        document.body.classList.toggle('dark-theme', toggle.checked);
        localStorage.setItem('theme', toggle.checked ? 'dark' : 'light');
    });
}

// Event Listeners
function setupEventListeners() {
    // File input change
    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            selectedFile = e.target.files[0];
            fileInfo.textContent = `Selected: ${selectedFile.name} (${formatBytes(selectedFile.size)})`;
            fileInfo.style.color = '#4a5568';
        }
    });
    
    // Drag and drop
    const uploadBox = document.getElementById('uploadBox');
    uploadBox.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadBox.style.borderColor = '#3a56d5';
        uploadBox.style.background = 'rgba(74, 108, 247, 0.05)';
    });
    
    uploadBox.addEventListener('dragleave', () => {
        uploadBox.style.borderColor = '#4a6cf7';
        uploadBox.style.background = '';
    });
    
    uploadBox.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadBox.style.borderColor = '#4a6cf7';
        uploadBox.style.background = '';
        
        if (e.dataTransfer.files.length > 0) {
            selectedFile = e.dataTransfer.files[0];
            fileInput.files = e.dataTransfer.files;
            fileInfo.textContent = `Selected: ${selectedFile.name} (${formatBytes(selectedFile.size)})`;
            fileInfo.style.color = '#4a5568';
        }
    });
    
    // Enter key in input
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });
}

// Format file size
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

// Check backend status
async function checkBackendStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/health`);
        if (response.ok) {
            setStatus('online', 'Backend connected');
        } else {
            setStatus('offline', 'Backend error');
        }
    } catch (error) {
        setStatus('offline', 'Cannot connect to backend');
    }
}

function setStatus(status, message) {
    if (status === 'online') {
        // Hide loader, show green dot
        statusLoader.style.display = 'none';
        statusDot.style.display = 'inline-block';
        statusDot.style.background = '#48bb78';
        statusText.textContent = message || 'Connected';
        statusText.style.color = '#48bb78';
    } else if (status === 'loading') {
        // Show loader, hide dot
        statusLoader.style.display = 'flex';
        statusDot.style.display = 'none';
        statusText.textContent = message || 'Initializing Backend';
        statusText.style.color = '#666';
    } else {
        // Offline – red dot, no loader
        statusLoader.style.display = 'none';
        statusDot.style.display = 'inline-block';
        statusDot.style.background = '#f56565';
        statusText.textContent = message || 'Disconnected';
        statusText.style.color = '#f56565';
    }
}

function clearChat() {
    if (!confirm("Clear all chat messages?")) return;

    const chatArea = document.getElementById("chatMessages");
    chatArea.innerHTML = "";

    addMessage("👋 Chat cleared. Ask a new question!", "bot");
}

// Sample Data Files
async function loadSampleFiles() {
    const sampleList = document.getElementById('sampleList');
    try {
        const response = await fetch(`${API_BASE_URL}/samples`);
        const data = await response.json();

        if (!response.ok || !data.samples || data.samples.length === 0) {
            sampleList.innerHTML = '<p class="sample-loading">No sample files available</p>';
            return;
        }

        sampleList.innerHTML = '';
        data.samples.forEach(file => {
            const item = document.createElement('div');
            item.className = 'sample-item';
            item.onclick = () => loadSampleData(file.name, item);
            item.innerHTML = `
                <div class="sample-item-info">
                    <i class="fas fa-file-csv"></i>
                    <div>
                        <div class="sample-item-name">${file.name}</div>
                        <div class="sample-item-size">${formatBytes(file.size)}</div>
                    </div>
                </div>
                <button class="sample-load-btn" onclick="event.stopPropagation(); loadSampleData('${file.name}', this.closest('.sample-item'))">
                    <i class="fas fa-play"></i> Load
                </button>
            `;
            sampleList.appendChild(item);
        });
    } catch (error) {
        sampleList.innerHTML = '<p class="sample-loading">Could not load samples</p>';
    }
}

async function loadSampleData(filename, itemEl) {
    const btn = itemEl.querySelector('.sample-load-btn');
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/samples/${encodeURIComponent(filename)}`);
        const result = await response.json();

        if (response.ok) {
            btn.innerHTML = '<i class="fas fa-check"></i> Loaded';
            btn.style.background = '#48bb78';

            addMessage(`✅ Sample file "${filename}" loaded with ${result.records_added} records. You can now ask questions about this data.`, 'bot');
            loadDataSummary();
        } else {
            btn.innerHTML = '<i class="fas fa-times"></i> Error';
            btn.style.background = '#f56565';
            setTimeout(() => { btn.innerHTML = originalHTML; btn.style.background = ''; btn.disabled = false; }, 2000);
        }
    } catch (error) {
        btn.innerHTML = '<i class="fas fa-times"></i> Error';
        btn.style.background = '#f56565';
        setTimeout(() => { btn.innerHTML = originalHTML; btn.style.background = ''; btn.disabled = false; }, 2000);
    }
}



// Upload file
async function uploadFile() {
    if (!selectedFile) {
        fileInfo.textContent = 'Please select a file first';
        fileInfo.style.color = '#f56565';
        return;
    }
    
    // Disable upload button and show loading
    const originalText = uploadBtn.innerHTML;
    uploadBtn.innerHTML = '<span class="loading"><span></span><span></span><span></span></span> Processing...';
    uploadBtn.disabled = true;
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    
    try {
        const response = await fetch(`${API_BASE_URL}/upload`, {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (response.ok) {
            fileInfo.textContent = `✓ ${selectedFile.name} processed successfully (${result.records_added} records)`;
            fileInfo.style.color = '#48bb78';
            
            // Add success message to chat
            addMessage(`Successfully processed ${selectedFile.name} with ${result.records_added} records. You can now ask questions about this data.`, 'bot');
            
            // Update data summary
            loadDataSummary();
        } else {
            fileInfo.textContent = `✗ Error: ${result.error}`;
            fileInfo.style.color = '#f56565';
        }
    } catch (error) {
        fileInfo.textContent = '✗ Network error. Is the backend running?';
        fileInfo.style.color = '#f56565';
    } finally {
        // Restore upload button
        uploadBtn.innerHTML = originalText;
        uploadBtn.disabled = false;
        
        // Clear selected file
        selectedFile = null;
        fileInput.value = '';
    }
}

// Load data summary
async function loadDataSummary() {
    try {
        const response = await fetch(`${API_BASE_URL}/data/summary`);
        const summary = await response.json();
        
        if (response.ok) {
            updateStatsDisplay(summary);
            renderProductInsights(summary.product_insights);
        }
    } catch (error) {
        console.error('Error loading data summary:', error);
    }
}

function formatINRShort(value) {
    if (!value || isNaN(value)) return "₹0";

    if (value >= 10000000) {
        return `₹${(value / 10000000).toFixed(2)} Crore`;
    }
    if (value >= 100000) {
        return `₹${(value / 100000).toFixed(2)} Lakh`;
    }
    if (value >= 1000) {
        return `₹${(value / 1000).toFixed(2)} Thousand`;
    }
    return `₹${value}`;
}

function formatProductMetric(value, metricKey) {
    if (value == null || isNaN(value)) return 'N/A';
    if (metricKey === 'quantity') return `${Math.round(value)} units`;
    return formatINRShort(value);
}

function renderProductInsights(productInsights) {
    const section = document.getElementById('salesInsightsSection');
    if (!section) return;

    if (!productInsights || productInsights.available === false) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'grid';

    const metricKey = productInsights.metric_used || 'revenue';
    const predicted = productInsights.predicted_highest_future_sales || {};

    document.getElementById('mostSoldProduct').textContent = productInsights.most_sold_product?.name || 'N/A';
    document.getElementById('mostSoldMeta').textContent =
        `${productInsights.metric_label || 'Metric'}: ${formatProductMetric(productInsights.most_sold_product?.value, metricKey)}`;

    document.getElementById('leastSoldProduct').textContent = productInsights.least_sold_product?.name || 'N/A';
    document.getElementById('leastSoldMeta').textContent =
        `${productInsights.metric_label || 'Metric'}: ${formatProductMetric(productInsights.least_sold_product?.value, metricKey)}`;

    document.getElementById('futureTopProduct').textContent = predicted.name || 'N/A';
    document.getElementById('futureTopMeta').textContent =
        `Projected Revenue: ${formatINRShort(predicted.projected_revenue || 0)} • Confidence: ${predicted.confidence || 'N/A'}`;

    const reasonsContainer = document.getElementById('futureTopReasons');
    if (reasonsContainer) {
        reasonsContainer.innerHTML = '';
        const reasons = Array.isArray(predicted.reasons) ? predicted.reasons.slice(0, 3) : [];
        if (reasons.length === 0) {
            const li = document.createElement('li');
            li.textContent = 'Not enough trend signals to generate reasons.';
            reasonsContainer.appendChild(li);
        } else {
            reasons.forEach((reason) => {
                const li = document.createElement('li');
                li.textContent = reason;
                reasonsContainer.appendChild(li);
            });
        }
    }

    renderProductTrendChart(
        'mostProductTrendChart',
        productInsights.most_sold_trend,
        productInsights.most_sold_product?.name || 'Most Sold Product',
        '#2b6cb0'
    );

    renderProductTrendChart(
        'leastProductTrendChart',
        productInsights.least_sold_trend,
        productInsights.least_sold_product?.name || 'Least Sold Product',
        '#d53f8c'
    );
}

function renderProductTrendChart(canvasId, trendData, label, lineColor) {
    if (typeof Chart === 'undefined') return;

    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const points = trendData && Array.isArray(trendData.points) ? trendData.points : [];
    const labels = points.map((point) => point.x);
    const values = points.map((point) => point.y);

    const importantIndices = new Set();
    if (values.length > 0) {
        importantIndices.add(0);
        importantIndices.add(values.length - 1);
    }

    for (let index = 1; index < values.length - 1; index += 1) {
        const prev = values[index - 1];
        const current = values[index];
        const next = values[index + 1];

        const isPeak = current > prev && current >= next;
        const isValley = current < prev && current <= next;

        if (isPeak || isValley) {
            importantIndices.add(index);
        }
    }

    if (values.length >= 2) {
        const maxValue = Math.max(...values);
        const minValue = Math.min(...values);
        importantIndices.add(values.indexOf(maxValue));
        importantIndices.add(values.indexOf(minValue));
    }

    if (productTrendCharts[canvasId]) {
        productTrendCharts[canvasId].destroy();
        productTrendCharts[canvasId] = null;
    }

    if (values.length < 2) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        return;
    }

    const metricType = trendData?.metric || 'revenue';
    const range = Math.max(...values) - Math.min(...values);
    const flatThreshold = Math.max(range * 0.05, 1);

    const getSegmentPalette = (context) => {
        const startValue = context.p0.parsed.y;
        const endValue = context.p1.parsed.y;
        const diff = endValue - startValue;

        if (Math.abs(diff) <= flatThreshold) {
            return {
                border: '#d69e2e',
                fill: 'rgba(214, 158, 46, 0.20)'
            };
        }

        if (diff > 0) {
            return {
                border: '#38a169',
                fill: 'rgba(56, 161, 105, 0.20)'
            };
        }

        return {
            border: '#e53e3e',
            fill: 'rgba(229, 62, 62, 0.20)'
        };
    };

    productTrendCharts[canvasId] = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [
                {
                    label,
                    data: values,
                    borderColor: lineColor,
                    backgroundColor: `${lineColor}33`,
                    fill: true,
                    tension: 0.3,
                    borderWidth: 2,
                    pointRadius: 2,
                    pointHoverRadius: 5,
                    segment: {
                        borderColor: (context) => getSegmentPalette(context).border,
                        backgroundColor: (context) => getSegmentPalette(context).fill
                    }
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: true,
                    callbacks: {
                        title: (tooltipItems) => tooltipItems[0]?.label || '',
                        label: (tooltipItem) => {
                            const value = tooltipItem.raw;
                            if (metricType === 'quantity') {
                                return `Units: ${Math.round(value)}`;
                            }
                            return `Revenue: ${formatINRShort(value)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        maxTicksLimit: 8,
                        color: '#718096',
                        callback: (tickValue, index) => {
                            if (!importantIndices.has(index)) return '';
                            const raw = labels[index] || '';
                            return raw;
                        }
                    },
                    grid: { display: false }
                },
                y: {
                    ticks: {
                        maxTicksLimit: 4,
                        color: '#718096',
                        callback: (value) => metricType === 'quantity'
                            ? Math.round(value)
                            : formatINRShort(value)
                    },
                    grid: { color: 'rgba(113, 128, 150, 0.2)' }
                }
            }
        }
    });
}


function updateStatsDisplay(summary) { 
    const totalRecordsEl = document.getElementById('totalRecords');
    const totalRevenueEl = document.getElementById('totalRevenue');
    const regionsCountEl = document.getElementById('regionsCount');
    const productsCountEl = document.getElementById('productsCount');

    const totalRecordsLabelEl = document.getElementById('totalRecordsLabel');
    const totalRevenueLabelEl = document.getElementById('totalRevenueLabel');
    const regionsCountLabelEl = document.getElementById('regionsCountLabel');
    const productsCountLabelEl = document.getElementById('productsCountLabel');

    totalRecordsLabelEl.textContent = 'Records';
    totalRevenueLabelEl.textContent = 'Revenue';
    regionsCountLabelEl.textContent = 'Regions';
    productsCountLabelEl.textContent = 'Products';

    const hasDynamicStats = summary.dynamic_stats && Array.isArray(summary.dynamic_stats);
    if (hasDynamicStats) {
        const statsById = Object.fromEntries(
            summary.dynamic_stats.map((entry) => [entry.id, entry])
        );

        const recordsStat = statsById.records;
        totalRecordsEl.textContent = recordsStat && recordsStat.value != null
            ? recordsStat.value
            : (summary.total_records || 0);

        const revenueStat = statsById.revenue;
        if (revenueStat && revenueStat.available === false) {
            totalRevenueEl.textContent = 'N/A';
            totalRevenueLabelEl.textContent = 'Revenue (Not in data)';
        } else {
            const revenueValue = revenueStat && revenueStat.value != null
                ? revenueStat.value
                : (summary.revenue ? summary.revenue.total : 0);
            totalRevenueEl.textContent = formatINRShort(revenueValue || 0);
        }

        const regionsStat = statsById.regions;
        if (regionsStat && regionsStat.available === false) {
            regionsCountEl.textContent = 'N/A';
            regionsCountLabelEl.textContent = (regionsStat.label || 'Regions') + ' (Not in data)';
        } else {
            regionsCountLabelEl.textContent = regionsStat?.label || 'Regions';
            const regionsValue = regionsStat && regionsStat.value != null
                ? regionsStat.value
                : (summary.categories ? summary.categories.regions.length : 0);
            regionsCountEl.textContent = regionsValue;
        }

        const productsStat = statsById.products;
        if (productsStat && productsStat.available === false) {
            productsCountEl.textContent = 'N/A';
            productsCountLabelEl.textContent = (productsStat.label || 'Products') + ' (Not in data)';
        } else {
            productsCountLabelEl.textContent = productsStat?.label || 'Products';
            const productsValue = productsStat && productsStat.value != null
                ? productsStat.value
                : (summary.categories ? summary.categories.products.length : 0);
            productsCountEl.textContent = productsValue;
        }

        return;
    }

    totalRecordsEl.textContent = summary.total_records || 0;
    totalRevenueEl.textContent = summary.revenue ? formatINRShort(summary.revenue.total) : '₹0';
    regionsCountEl.textContent = summary.categories ? summary.categories.regions.length : 0;
    productsCountEl.textContent = summary.categories ? summary.categories.products.length : 0;
}


// Clear all data
async function clearData() {
    if (!confirm('Are you sure you want to clear all data?')) return;
    
    try {
        const response = await fetch(`${API_BASE_URL}/clear`, {
            method: 'POST'
        });
        
        if (response.ok) {
            fileInfo.textContent = 'All data cleared successfully';
            fileInfo.style.color = '#48bb78';
            
            // Update stats
            updateStatsDisplay({
                total_records: 0,
                revenue: { total: 0 },
                categories: { regions: [], products: [] },
                dynamic_stats: [
                    { id: 'records', label: 'Records', value: 0, type: 'count' },
                    { id: 'revenue', label: 'Revenue', value: null, type: 'currency', available: false },
                    { id: 'regions', label: 'Regions', value: null, type: 'count', available: false },
                    { id: 'products', label: 'Products', value: null, type: 'count', available: false }
                ]
            });
            renderProductInsights(null);
            
            // Add message to chat
            addMessage('All data has been cleared. You can upload new files to start fresh.', 'bot');

            // Reset predictions tab
            window._predictionsLoaded = false;
            _predictionsCache = null;
            const predContent = document.getElementById('predictionsContent');
            const predEmpty = document.getElementById('predictionsEmpty');
            if (predContent) predContent.style.display = 'none';
            if (predEmpty) {
                predEmpty.style.display = 'block';
                predEmpty.querySelector('h3').textContent = 'No Data Loaded';
                predEmpty.querySelector('p').textContent = 'Upload a CSV/Excel file first, then switch here to see AI-generated predictions, alternative strategies, and improvement recommendations.';
            }
        }
    } catch (error) {
        console.error('Error clearing data:', error);
    }
}

// Chat functions
function askQuestion(question) {
    userInput.value = question;
    sendMessage();
}

async function sendMessage() {
    const query = userInput.value.trim();
    if (!query) return;
    
    // Add user message
    addMessage(query, 'user');
    
    // Clear input
    userInput.value = '';
    
    // Show loading
    const loadingId = addLoadingMessage();
    
    try {
        const response = await fetch(`${API_BASE_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query })
        });
        
        const result = await response.json();
        
        // Remove loading
        removeMessage(loadingId);
        
        if (response.ok) {
            // Add bot response
            addMessage(result.response, 'bot');
            
            // Update stats if they changed
            if (result.data_summary) {
                updateStatsDisplay(result.data_summary);
                renderProductInsights(result.data_summary.product_insights);
            }
        } else {
            addMessage(`Error: ${result.error}`, 'bot');
        }
    } catch (error) {
        removeMessage(loadingId);
        addMessage('Cannot connect to the backend server. Make sure it is running on port 5000.', 'bot');
    }
}

function addMessage(content, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;
    
    const avatarIcon = sender === 'user' ? 'fas fa-user' : 'fas fa-robot';
    const senderName = sender === 'user' ? 'You' : 'Sales Assistant';
    
    // Format content with line breaks
    const formattedContent = content.replace(/\n/g, '<br>');
    
    messageDiv.innerHTML = `
        <div class="avatar">
            <i class="${avatarIcon}"></i>
        </div>
        <div class="content">
            <div class="name">${senderName}</div>
            <p>${formattedContent}</p>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return messageDiv.id;
}

function addLoadingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.id = 'loading-' + Date.now();
    messageDiv.className = 'message bot';
    
    messageDiv.innerHTML = `
        <div class="avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="content">
            <div class="name">Sales Assistant</div>
            <p><span class="loading"><span></span><span></span><span></span></span> Analyzing your question...</p>
        </div>
    `;
    
    chatMessages.appendChild(messageDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    return messageDiv.id;
}

function removeMessage(messageId) {
    const element = document.getElementById(messageId);
    if (element) {
        element.remove();
    }
}

function handleKeyPress(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
}
// Add to existing script.js - After the existing functions

// Display charts in chat
function displayCharts(charts) {
    if (!charts || Object.keys(charts).length === 0) {
        return;
    }
    
    const chatMessages = document.getElementById('chatMessages');
    
    // Create a message container for charts
    const chartMessage = document.createElement('div');
    chartMessage.className = 'message bot';
    chartMessage.id = 'charts-' + Date.now();
    
    let chartsHTML = `
        <div class="avatar">
            <i class="fas fa-chart-bar"></i>
        </div>
        <div class="content">
            <div class="name">Visualizations</div>
            <p>Here are some charts generated from your data:</p>
            <div class="charts-container">
    `;
    
    // Add each chart
    Object.entries(charts).forEach(([chartName, chartData], index) => {
        const chartLabels = {
            'revenue_trend': 'Revenue Trend Over Time',
            'regional_sales': 'Sales by Region',
            'product_performance': 'Product Performance',
            'sales_distribution': 'Sales Distribution',
            'monthly_trend': 'Monthly Revenue Trend',
            'pipeline_stages': 'Pipeline Stages'
        };
        
        const label = chartLabels[chartName] || chartName.replace('_', ' ').toUpperCase();
        
        chartsHTML += `
            <div class="chart-card">
                <h4>${label}</h4>
                <img src="data:image/png;base64,${chartData}" 
                     alt="${label}" 
                     class="chart-image"
                     onclick="showFullChart('${chartName}', '${chartData}')">
                <div class="chart-actions">
                    <button onclick="downloadChart('${chartName}', '${chartData}')">
                        <i class="fas fa-download"></i> Download
                    </button>
                </div>
            </div>
        `;
    });
    
    chartsHTML += `
            </div>
            <p class="chart-note">
                <i class="fas fa-info-circle"></i>
                Click on any chart to view it full size
            </p>
        </div>
    `;
    
    chartMessage.innerHTML = chartsHTML;
    chatMessages.appendChild(chartMessage);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Add CSS for charts if not already added
    addChartStyles();
}

// Show full-size chart
function showFullChart(chartName, chartData) {
    const modal = document.createElement('div');
    modal.className = 'chart-modal';
    modal.innerHTML = `
        <div class="chart-modal-content">
            <div class="chart-modal-header">
                <h3>${chartName.replace('_', ' ').toUpperCase()}</h3>
                <button class="close-chart" onclick="this.parentElement.parentElement.parentElement.remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
            <div class="chart-modal-body">
                <img src="data:image/png;base64,${chartData}" 
                     alt="${chartName}" 
                     class="full-chart-image">
            </div>
            <div class="chart-modal-footer">
                <button onclick="downloadChart('${chartName}', '${chartData}')">
                    <i class="fas fa-download"></i> Download PNG
                </button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}

// Download chart
function downloadChart(chartName, chartData) {
    const link = document.createElement('a');
    link.href = 'data:image/png;base64,' + chartData;
    link.download = `sales_chart_${chartName}_${new Date().toISOString().split('T')[0]}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// Add chart styles dynamically
function addChartStyles() {
    if (document.getElementById('chart-styles')) {
        return;
    }
    
    const style = document.createElement('style');
    style.id = 'chart-styles';
    style.textContent = `
        .charts-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 15px 0;
        }
        
        .chart-card {
            background: white;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        
        .chart-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        
        .chart-card h4 {
            margin: 0 0 10px 0;
            font-size: 14px;
            color: #2d3748;
            text-align: center;
        }
        
        .chart-image {
            width: 100%;
            height: 200px;
            object-fit: contain;
            cursor: pointer;
            border-radius: 4px;
            border: 1px solid #e2e8f0;
            transition: transform 0.3s;
        }
        
        .chart-image:hover {
            transform: scale(1.02);
        }
        
        .chart-actions {
            margin-top: 10px;
            text-align: center;
        }
        
        .chart-actions button {
            background: #4a6cf7;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 12px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 5px;
        }
        
        .chart-note {
            font-size: 12px;
            color: #718096;
            margin-top: 10px;
            display: flex;
            align-items: center;
            gap: 5px;
        }
        
        .chart-modal {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            animation: fadeIn 0.3s;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        
        .chart-modal-content {
            background: white;
            border-radius: 12px;
            width: 90%;
            max-width: 800px;
            max-height: 90vh;
            overflow: hidden;
            animation: slideUp 0.3s;
        }
        
        @keyframes slideUp {
            from { transform: translateY(50px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        
        .chart-modal-header {
            padding: 20px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .chart-modal-header h3 {
            margin: 0;
            color: #2d3748;
        }
        
        .close-chart {
            background: none;
            border: none;
            font-size: 20px;
            color: #718096;
            cursor: pointer;
            padding: 5px;
        }
        
        .chart-modal-body {
            padding: 20px;
            text-align: center;
            max-height: 60vh;
            overflow-y: auto;
        }
        
        .full-chart-image {
            max-width: 100%;
            max-height: 60vh;
            object-fit: contain;
        }
        
        .chart-modal-footer {
            padding: 15px 20px;
            border-top: 1px solid #e2e8f0;
            text-align: center;
        }
        
        .chart-modal-footer button {
            background: #4a6cf7;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 6px;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        
        @media (max-width: 768px) {
            .charts-container {
                grid-template-columns: 1fr;
            }
            
            .chart-modal-content {
                width: 95%;
                max-height: 85vh;
            }

            .chart-image {
                height: 160px;
            }

            .chart-modal-body {
                padding: 12px;
            }

            .full-chart-image {
                max-height: 50vh;
            }

            .chart-card {
                padding: 10px;
            }

            .chart-card h4 {
                font-size: 13px;
            }
        }
    `;
    
    document.head.appendChild(style);
}

// Update the sendMessage function to handle visualizations
// Find the existing sendMessage function and update it:

async function sendMessage() {
    const query = userInput.value.trim();
    if (!query) return;
    
    // Add user message
    addMessage(query, 'user');
    
    // Clear input
    userInput.value = '';
    
    // Show loading
    const loadingId = addLoadingMessage();
    
    try {
        const response = await fetch(`${API_BASE_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ query })
        });
        
        const result = await response.json();
        
        // Remove loading
        removeMessage(loadingId);
        
        if (response.ok) {
            // Add bot response
            addMessage(result.response, 'bot');
            
            // Display charts if available
            if (result.visualizations && Object.keys(result.visualizations).length > 0) {
                displayCharts(result.visualizations);
            }
            
            // Update stats
            if (result.data_summary) {
                updateStatsDisplay(result.data_summary);
                renderProductInsights(result.data_summary.product_insights);
            }
        } else {
            addMessage(`Error: ${result.error}`, 'bot');
        }
    } catch (error) {
        removeMessage(loadingId);
        addMessage('Cannot connect to the backend server. Make sure it is running on port 5000.', 'bot');
    }
}

function formatINR(value) {
    if (value >= 10000000) {
        return `₹${(value / 10000000).toFixed(2)} Crore`;
    } else if (value >= 100000) {
        return `₹${(value / 100000).toFixed(2)} Lakh`;
    } else if (value >= 1000) {
        return `₹${(value / 1000).toFixed(2)} Thousand`;
    } else {
        return `₹${value}`;
    }
}


// Add this function to script.js
async function generateVisualizations() {
    try {
        const response = await fetch(`${API_BASE_URL}/visualizations`);
        const result = await response.json();
        
        if (response.ok) {
            // Add message about charts
            addMessage(`Generated ${result.charts ? Object.keys(result.charts).length : 0} visualization(s) from the data.`, 'bot');
            
            // Display the charts
            if (result.charts) {
                displayCharts(result.charts);
            }
        } else {
            addMessage(`Error generating charts: ${result.error}`, 'bot');
        }
    } catch (error) {
        addMessage('Error generating visualizations. Make sure backend is running.', 'bot');
    }
}

// ============ TAB SWITCHING ============
function switchTab(tab) {
    // Update tab buttons
    document.getElementById('tabChat').classList.toggle('active', tab === 'chat');
    document.getElementById('tabPredictions').classList.toggle('active', tab === 'predictions');

    // Update tab content
    document.getElementById('chatTab').classList.toggle('active', tab === 'chat');
    document.getElementById('predictionsTab').classList.toggle('active', tab === 'predictions');

    // Auto-load predictions on first visit if data is available
    if (tab === 'predictions' && !window._predictionsLoaded) {
        const totalRecords = document.getElementById('totalRecords');
        if (totalRecords && parseInt(totalRecords.textContent) > 0) {
            loadPredictions();
        }
    }
}

// ============ PREDICTIONS ============
let _predictionsCache = null;

async function loadPredictions() {
    const loadingEl = document.getElementById('predictionsLoading');
    const emptyEl = document.getElementById('predictionsEmpty');
    const contentEl = document.getElementById('predictionsContent');
    const refreshBtn = document.getElementById('refreshPredictionsBtn');

    // Show loading
    loadingEl.style.display = 'flex';
    emptyEl.style.display = 'none';
    contentEl.style.display = 'none';
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = '<i class="fas fa-sync-alt fa-spin"></i> Generating...';

    try {
        const response = await fetch(`${API_BASE_URL}/predictions`);
        const result = await response.json();

        if (!response.ok || !result.available) {
            loadingEl.style.display = 'none';
            emptyEl.style.display = 'block';
            const emptyH3 = emptyEl.querySelector('h3');
            const emptyP = emptyEl.querySelector('p');
            if (!response.ok) {
                emptyH3.textContent = 'Generation Failed';
                emptyP.textContent = result.message || 'AI could not generate predictions. Please try again.';
            } else {
                emptyH3.textContent = 'No Data';
                emptyP.textContent = result.message || 'No data available for predictions.';
            }
            return;
        }

        _predictionsCache = result.predictions;
        window._predictionsLoaded = true;
        renderPredictions(result.predictions);

        loadingEl.style.display = 'none';
        contentEl.style.display = 'block';

    } catch (error) {
        console.error('Predictions error:', error);
        loadingEl.style.display = 'none';
        emptyEl.style.display = 'block';
        emptyEl.querySelector('h3').textContent = 'Connection Error';
        emptyEl.querySelector('p').textContent = 'Could not reach the backend. Make sure it is running and try again.';
    } finally {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
    }
}

function renderPredictions(predictions) {
    const container = document.getElementById('predictionsContent');
    container.innerHTML = '';

    const sectionConfig = [
        { key: 'sales_forecast', icon: 'fas fa-chart-line', cssClass: 'forecast' },
        { key: 'product_predictions', icon: 'fas fa-box-open', cssClass: 'products' },
        { key: 'regional_predictions', icon: 'fas fa-map-marker-alt', cssClass: 'regions' },
        { key: 'alternatives', icon: 'fas fa-lightbulb', cssClass: 'alternatives' },
        { key: 'improvements', icon: 'fas fa-rocket', cssClass: 'improvements' }
    ];

    sectionConfig.forEach(({ key, icon, cssClass }) => {
        const section = predictions[key];
        if (!section || !section.items || section.items.length === 0) return;

        const sectionEl = document.createElement('div');
        sectionEl.className = `pred-section ${cssClass}`;

        let itemsHTML = '';
        section.items.forEach(item => {
            const badges = buildBadges(item);
            itemsHTML += `
                <div class="pred-item">
                    <div class="pred-item-header">
                        <div class="pred-item-label">${escapeHTML(item.label)}</div>
                        ${item.value ? `<div class="pred-item-value">${escapeHTML(item.value)}</div>` : ''}
                    </div>
                    <div class="pred-item-detail">${escapeHTML(item.detail)}</div>
                    <div class="pred-item-meta">${badges}</div>
                </div>
            `;
        });

        sectionEl.innerHTML = `
            <div class="pred-section-title">
                <i class="${icon}"></i> ${escapeHTML(section.title)}
            </div>
            ${itemsHTML}
        `;

        container.appendChild(sectionEl);
    });

    if (container.children.length === 0) {
        container.innerHTML = '<p style="text-align:center;color:#a0aec0;padding:40px;">No predictions could be generated from this data.</p>';
    }
}

function buildBadges(item) {
    let html = '';
    if (item.trend) {
        const trendIcon = item.trend === 'up' ? 'fa-arrow-up' : item.trend === 'down' ? 'fa-arrow-down' : 'fa-minus';
        html += `<span class="pred-badge trend-${item.trend}"><i class="fas ${trendIcon}"></i> ${item.trend}</span>`;
    }
    if (item.confidence) {
        html += `<span class="pred-badge confidence-${item.confidence.toLowerCase()}">${item.confidence} confidence</span>`;
    }
    if (item.impact) {
        html += `<span class="pred-badge impact-${item.impact.toLowerCase()}"><i class="fas fa-bolt"></i> ${item.impact} impact</span>`;
    }
    if (item.category) {
        html += `<span class="pred-badge category"><i class="fas fa-tag"></i> ${item.category}</span>`;
    }
    if (item.expected_boost) {
        html += `<span class="pred-badge boost"><i class="fas fa-chart-line"></i> ${escapeHTML(item.expected_boost)}</span>`;
    }
    return html;
}

function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}