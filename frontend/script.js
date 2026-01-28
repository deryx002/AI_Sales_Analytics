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