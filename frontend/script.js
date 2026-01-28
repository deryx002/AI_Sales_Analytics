// API Configuration
const API_BASE_URL = 'http://localhost:5000/api';

// DOM Elements
const fileInput = document.getElementById('fileInput');
const uploadBtn = document.getElementById('uploadBtn');
const fileInfo = document.getElementById('fileInfo');
const chatMessages = document.getElementById('chatMessages');
const userInput = document.getElementById('userInput');
const statusIndicator = document.getElementById('statusIndicator');
const statusDot = document.querySelector('.status-dot');

// State
let selectedFile = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    checkBackendStatus();
    loadDataSummary();
    setupEventListeners();
});

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
    const statusText = statusIndicator.querySelector('span:last-child');
    
    if (status === 'online') {
        statusDot.style.background = '#48bb78';
        statusText.textContent = message || 'Connected';
        statusText.style.color = '#48bb78';
    } else {
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
        }
    } catch (error) {
        console.error('Error loading data summary:', error);
    }
}

function updateStatsDisplay(summary) {
    document.getElementById('totalRecords').textContent = summary.total_records || 0;
    document.getElementById('totalRevenue').textContent = summary.revenue ? 
        `$${summary.revenue.total.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : '$0';
    document.getElementById('regionsCount').textContent = summary.categories ? summary.categories.regions.length : 0;
    document.getElementById('productsCount').textContent = summary.categories ? summary.categories.products.length : 0;
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
                categories: { regions: [], products: [] }
            });
            
            // Add message to chat
            addMessage('All data has been cleared. You can upload new files to start fresh.', 'bot');
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
                updateStatsDisplay({
                    total_records: result.data_summary.total_records,
                    revenue: { total: result.data_summary.total_revenue },
                    categories: { 
                        regions: Array(result.data_summary.regions_count || 0),
                        products: Array(result.data_summary.products_count || 0)
                    }
                });
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
                updateStatsDisplay({
                    total_records: result.data_summary.total_records,
                    revenue: { total: result.data_summary.total_revenue },
                    categories: { 
                        regions: Array(result.data_summary.regions_count || 0),
                        products: Array(result.data_summary.products_count || 0)
                    }
                });
            }
        } else {
            addMessage(`Error: ${result.error}`, 'bot');
        }
    } catch (error) {
        removeMessage(loadingId);
        addMessage('Cannot connect to the backend server. Make sure it is running on port 5000.', 'bot');
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