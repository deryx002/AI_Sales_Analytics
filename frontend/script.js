// ============================================================
//  API & AUTH CONFIG
// ============================================================
const API_BASE_URL = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost'
    ? 'http://127.0.0.1:5000/api'
    : 'https://ai-sales-analytics.onrender.com/api';

// Multi-user state
let currentUsername = localStorage.getItem('username') || '';
let currentDatasetId = '';

// If not logged in, redirect to login page
if (!currentUsername) {
    window.location.href = 'login.html';
}

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
const datasetSelector = document.getElementById('datasetSelector');

// State
let selectedFile = null;
const productTrendCharts = {};

// ============================================================
//  INITIALIZE
// ============================================================
document.addEventListener('DOMContentLoaded', async () => {
    initThemeToggle();
    initGoTopButton();
    setupEventListeners();

    // Show username in UI
    const usernameDisplay = document.getElementById('usernameDisplay');
    if (usernameDisplay) {
        usernameDisplay.textContent = currentUsername;
    }

    // Reset predictions state
    window._predictionsLoaded = false;
    _predictionsCache = null;

    checkBackendStatus();
    loadSampleFiles();
    loadUserDatasets(); // Load user's datasets from MongoDB

    // Open the Upload section by default
    toggleSidebarSection('uploadSection', true);
});

// ============================================================
//  SIDEBAR TOGGLE HELPERS
// ============================================================
function toggleSidebarSection(sectionId, forceOpen) {
    const layout = document.querySelector('.app-layout');
    const isCollapsed = layout && layout.classList.contains('sidebar-collapsed');

    // If sidebar is collapsed, expand it first and open this section
    if (isCollapsed) {
        layout.classList.remove('sidebar-collapsed');
        localStorage.setItem('sidebarCollapsed', '0');
        // Fold all sections, then open the one that was clicked
        foldAllSidebarSections();
        const body = document.getElementById(sectionId);
        const icon = document.getElementById(sectionId + 'Icon');
        if (body) body.classList.add('open');
        if (icon) icon.classList.add('open');
        return;
    }

    const body = document.getElementById(sectionId);
    const icon = document.getElementById(sectionId + 'Icon');
    if (!body) return;

    if (forceOpen === true) {
        body.classList.add('open');
        if (icon) icon.classList.add('open');
    } else if (forceOpen === false) {
        body.classList.remove('open');
        if (icon) icon.classList.remove('open');
    } else {
        body.classList.toggle('open');
        if (icon) icon.classList.toggle('open');
    }
}

function foldAllSidebarSections() {
    document.querySelectorAll('.sidebar-section-body').forEach(body => {
        body.classList.remove('open');
    });
    document.querySelectorAll('.sidebar-toggle-icon').forEach(icon => {
        icon.classList.remove('open');
    });
}

function handleCollapsedSidebarClick(action) {
    const layout = document.querySelector('.app-layout');
    const isCollapsed = layout && layout.classList.contains('sidebar-collapsed');
    if (isCollapsed) {
        // Expand sidebar first
        layout.classList.remove('sidebar-collapsed');
        localStorage.setItem('sidebarCollapsed', '0');
        foldAllSidebarSections();
    }
    // Execute the action
    if (action === 'charts') {
        generateVisualizations();
    }
}

function toggleMobileSidebar() {
    const sidebar = document.querySelector('.left-sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    if (!sidebar) return;
    sidebar.classList.toggle('mobile-open');
    if (overlay) overlay.classList.toggle('visible');
}

function toggleSidebarCollapse() {
    const layout = document.querySelector('.app-layout');
    if (!layout) return;
    const willCollapse = !layout.classList.contains('sidebar-collapsed');
    layout.classList.toggle('sidebar-collapsed');
    localStorage.setItem('sidebarCollapsed', willCollapse ? '1' : '0');
    // When expanding (uncollapsing), fold all sub-sections
    if (!willCollapse) {
        foldAllSidebarSections();
    }
}

function startNewChat() {
    currentDatasetId = '';
    datasetSelector.value = '';
    chatMessages.innerHTML = '';
    addMessage('Start a new conversation! Upload a dataset or pick one from your history.', 'bot');
    // Show quick-question chips again
    const qq = document.getElementById('quickQuestions');
    if (qq) qq.style.display = '';
    updateChatHistoryActive();
    // Reset stats
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
    // Reset predictions
    window._predictionsLoaded = false;
    _predictionsCache = null;
    const predContent = document.getElementById('predictionsContent');
    const predEmpty = document.getElementById('predictionsEmpty');
    if (predContent) predContent.style.display = 'none';
    if (predEmpty) predEmpty.style.display = 'block';
    const pdfBtn = document.getElementById('downloadPdfBtn');
    if (pdfBtn) pdfBtn.style.display = 'none';
}

// ============================================================
//  LOGOUT
// ============================================================
function logoutUser() {
    localStorage.removeItem('username');
    window.location.href = 'login.html';
}

// ============================================================
//  DATASET MANAGEMENT
// ============================================================
async function loadUserDatasets() {
    if (!currentUsername) return;
    try {
        const res = await fetch(`${API_BASE_URL}/datasets/${encodeURIComponent(currentUsername)}`);
        const datasets = await res.json();

        datasetSelector.innerHTML = '<option value="">-- Select a dataset --</option>';

        if (Array.isArray(datasets) && datasets.length > 0) {
            datasets.forEach(ds => {
                const opt = document.createElement('option');
                opt.value = ds.dataset_id;
                opt.textContent = `${ds.filename} (${ds.rows} rows) - ${new Date(ds.upload_time).toLocaleDateString()}`;
                datasetSelector.appendChild(opt);
            });
            // Do NOT auto-select — start with a fresh empty chat
            currentDatasetId = '';
        } else {
            currentDatasetId = '';
        }
        // Refresh sidebar chat history list
        loadChatHistorySidebar();
    } catch (err) {
        console.error('Error loading user datasets:', err);
    }
}

function onDatasetChange() {
    currentDatasetId = datasetSelector.value;
    if (currentDatasetId) {
        loadDataSummary();
        loadChatHistory();
        // Reset predictions when switching datasets
        window._predictionsLoaded = false;
        _predictionsCache = null;
        const predContent = document.getElementById('predictionsContent');
        const predEmpty = document.getElementById('predictionsEmpty');
        if (predContent) predContent.style.display = 'none';
        if (predEmpty) predEmpty.style.display = 'block';
        const pdfBtn = document.getElementById('downloadPdfBtn');
        if (pdfBtn) pdfBtn.style.display = 'none';
    } else {
        // Clear stats display
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
    }
    // Update active state in sidebar chat history
    updateChatHistoryActive();
}

async function deleteCurrentDataset() {
    if (!currentDatasetId || !currentUsername) return;
    if (!confirm('Delete this dataset and all its chat history?')) return;
    await _doDeleteDataset(currentDatasetId);
}

async function deleteDatasetById(datasetId, filename) {
    if (!datasetId || !currentUsername) return;
    if (!confirm(`Delete "${filename}" and all its chat history?`)) return;
    await _doDeleteDataset(datasetId);
}

async function _doDeleteDataset(datasetId) {
    try {
        const res = await fetch(
            `${API_BASE_URL}/datasets/${encodeURIComponent(currentUsername)}/${encodeURIComponent(datasetId)}`,
            { method: 'DELETE' }
        );
        if (res.ok) {
            addMessage('Dataset deleted successfully.', 'bot');
            if (datasetId === currentDatasetId) {
                currentDatasetId = '';
            }
            loadUserDatasets();
        } else {
            const data = await res.json();
            addMessage(`Error deleting dataset: ${data.error || 'Unknown error'}`, 'bot');
        }
    } catch (err) {
        addMessage('Network error while deleting dataset.', 'bot');
    }
}

// ============================================================
//  CHAT HISTORY (per dataset)
// ============================================================
async function loadChatHistory() {
    if (!currentUsername || !currentDatasetId) return;

    // Clear existing chat messages except the welcome message
    chatMessages.innerHTML = '';

    try {
        const res = await fetch(
            `${API_BASE_URL}/chats/${encodeURIComponent(currentUsername)}/${encodeURIComponent(currentDatasetId)}`
        );
        const chats = await res.json();

        if (Array.isArray(chats) && chats.length > 0) {
            // Show a brief intro
            addMessage('Chat history loaded for this dataset.', 'bot');
            chats.forEach(chat => {
                addMessage(chat.query, 'user');
                addMessage(chat.response, 'bot');
            });
        } else {
            addMessage('Hello! Ask questions about this dataset.', 'bot');
        }
    } catch (err) {
        addMessage('Hello! Ask questions about this dataset.', 'bot');
    }
}

// ============================================================
//  CHAT HISTORY SIDEBAR (list of all user datasets + previews)
// ============================================================
async function loadChatHistorySidebar() {
    const listEl = document.getElementById('chatHistoryList');
    if (!listEl || !currentUsername) return;

    try {
        // Only fetch the dataset list — NO per-dataset chat API calls
        const res = await fetch(`${API_BASE_URL}/datasets/${encodeURIComponent(currentUsername)}`);
        const datasets = await res.json();

        if (!Array.isArray(datasets) || datasets.length === 0) {
            listEl.innerHTML = `
                <div class="chat-history-empty">
                    <i class="fas fa-comments"></i>
                    <p>No previous chats</p>
                </div>`;
            return;
        }

        const items = datasets.map(ds => {
            const uploadDate = new Date(ds.upload_time);
            const dateStr = uploadDate.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
            const isActive = ds.dataset_id === currentDatasetId;

            return `
                <div class="chat-history-item${isActive ? ' active' : ''}"
                     onclick="switchToDataset('${ds.dataset_id}')" title="${ds.filename}">
                    <div class="ch-icon"><i class="fas fa-file-alt"></i></div>
                    <div class="ch-info">
                        <div class="ch-name">${ds.filename}</div>
                        <div class="ch-meta">${dateStr} · ${ds.rows} rows</div>
                    </div>
                    <button class="ch-delete-btn" onclick="event.stopPropagation(); deleteDatasetById('${ds.dataset_id}', '${ds.filename.replace(/'/g, "\\'")}')" title="Delete dataset">
                        <i class="fas fa-trash-alt"></i>
                    </button>
                </div>`;
        });

        listEl.innerHTML = items.join('');
    } catch (err) {
        console.error('Error loading chat history sidebar:', err);
    }
}

function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.substring(0, max) + '…' : str;
}

function switchToDataset(datasetId) {
    currentDatasetId = datasetId;
    datasetSelector.value = datasetId;
    // Load this dataset's data summary + chat history
    if (currentDatasetId) {
        loadDataSummary();
        loadChatHistory();
        // Reset predictions
        window._predictionsLoaded = false;
        _predictionsCache = null;
        const predContent = document.getElementById('predictionsContent');
        const predEmpty = document.getElementById('predictionsEmpty');
        if (predContent) predContent.style.display = 'none';
        if (predEmpty) predEmpty.style.display = 'block';
        const pdfBtn = document.getElementById('downloadPdfBtn');
        if (pdfBtn) pdfBtn.style.display = 'none';
    }
    updateChatHistoryActive();
    // Close mobile sidebar if open
    const sidebar = document.querySelector('.left-sidebar');
    if (sidebar && sidebar.classList.contains('mobile-open')) {
        toggleMobileSidebar();
    }
}

function updateChatHistoryActive() {
    const items = document.querySelectorAll('.chat-history-item');
    items.forEach(item => {
        const dsId = item.getAttribute('onclick')?.match(/'([^']+)'/)?.[1];
        if (dsId === currentDatasetId) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
}

// ============================================================
//  GO TO TOP & THEME
// ============================================================
function initGoTopButton() {
    const btn = document.getElementById('goTopBtn');
    if (!btn) return;
    window.addEventListener('scroll', () => {
        btn.classList.toggle('visible', window.scrollY > 300);
    }, { passive: true });
}

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

// ============================================================
//  EVENT LISTENERS
// ============================================================
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

// ============================================================
//  UTILITIES
// ============================================================
function formatBytes(bytes, decimals = 2) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function formatINRShort(value) {
    if (!value || isNaN(value)) return "₹0";
    if (value >= 10000000) return `₹${(value / 10000000).toFixed(2)} Crore`;
    if (value >= 100000) return `₹${(value / 100000).toFixed(2)} Lakh`;
    if (value >= 1000) return `₹${(value / 1000).toFixed(2)} Thousand`;
    return `₹${value}`;
}

function formatINR(value) {
    return formatINRShort(value);
}

function formatProductMetric(value, metricKey) {
    if (value == null || isNaN(value)) return 'N/A';
    if (metricKey === 'quantity') return `${Math.round(value)} units`;
    return formatINRShort(value);
}

function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ============================================================
//  BACKEND STATUS
// ============================================================
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
        statusLoader.style.display = 'none';
        statusDot.style.display = 'inline-block';
        statusDot.style.background = '#48bb78';
        statusText.textContent = message || 'Connected';
        statusText.style.color = '#48bb78';
    } else if (status === 'loading') {
        statusLoader.style.display = 'flex';
        statusDot.style.display = 'none';
        statusText.textContent = message || 'Initializing Backend';
        statusText.style.color = '#666';
    } else {
        statusLoader.style.display = 'none';
        statusDot.style.display = 'inline-block';
        statusDot.style.background = '#f56565';
        statusText.textContent = message || 'Disconnected';
        statusText.style.color = '#f56565';
    }
}

// ============================================================
//  CLEAR CHAT
// ============================================================
function clearChat() {
    if (!confirm("Clear all chat messages?")) return;
    chatMessages.innerHTML = "";
    addMessage("Chat cleared. Ask a new question!", "bot");
}

// ============================================================
//  SAMPLE DATA
// ============================================================
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
            item.dataset.filename = file.name;
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

let _sampleLoadInProgress = false;
let _loadedSampleFilename = null;

async function loadSampleData(filename, itemEl) {
    if (_sampleLoadInProgress) return;
    _sampleLoadInProgress = true;
    const btn = itemEl.querySelector('.sample-load-btn');
    const originalHTML = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
    btn.disabled = true;

    try {
        let url = `${API_BASE_URL}/samples/${encodeURIComponent(filename)}`;
        if (currentUsername) {
            url += `?username=${encodeURIComponent(currentUsername)}`;
        }
        const response = await fetch(url);
        const result = await response.json();

        if (response.ok) {
            _loadedSampleFilename = filename;

            // Mark this item as loaded and show Unload button
            btn.innerHTML = '<i class="fas fa-times-circle"></i> Unload';
            btn.style.background = '#e53e3e';
            btn.disabled = false;
            btn.onclick = (e) => { e.stopPropagation(); unloadSampleData(filename, itemEl); };
            itemEl.classList.add('sample-loaded');

            // Disable other sample items' Load buttons
            document.querySelectorAll('.sample-item').forEach(otherItem => {
                if (otherItem !== itemEl) {
                    const otherBtn = otherItem.querySelector('.sample-load-btn');
                    if (otherBtn) otherBtn.disabled = true;
                }
            });

            if (result.dataset_id) {
                currentDatasetId = result.dataset_id;
                await loadUserDatasets();
                datasetSelector.value = currentDatasetId;
            }

            addMessage(`Sample file "${filename}" loaded with ${result.records_added} records. You can now ask questions about this data.`, 'bot');
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
    } finally {
        _sampleLoadInProgress = false;
    }
}

async function unloadSampleData(filename, itemEl) {
    if (_sampleLoadInProgress) return;
    _sampleLoadInProgress = true;
    const btn = itemEl.querySelector('.sample-load-btn');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Unloading...';
    btn.disabled = true;

    try {
        const response = await fetch(`${API_BASE_URL}/clear`, { method: 'POST' });

        if (response.ok) {
            _loadedSampleFilename = null;
            currentDatasetId = '';
            if (datasetSelector) datasetSelector.value = '';

            // Reset stats
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

            // Reset all sample items back to Load state
            document.querySelectorAll('.sample-item').forEach(item => {
                item.classList.remove('sample-loaded');
                const itemBtn = item.querySelector('.sample-load-btn');
                const itemFilename = item.dataset.filename;
                if (itemBtn) {
                    itemBtn.innerHTML = '<i class="fas fa-play"></i> Load';
                    itemBtn.style.background = '';
                    itemBtn.disabled = false;
                    itemBtn.onclick = (e) => { e.stopPropagation(); loadSampleData(itemFilename, item); };
                }
            });

            addMessage(`Sample file "${filename}" has been unloaded. You can now load a different dataset.`, 'bot');
            await loadUserDatasets();
        }
    } catch (error) {
        console.error('Error unloading sample data:', error);
        btn.innerHTML = '<i class="fas fa-times-circle"></i> Unload';
        btn.style.background = '#e53e3e';
        btn.disabled = false;
    } finally {
        _sampleLoadInProgress = false;
    }
}

// ============================================================
//  UPLOAD FILE (multi-user)
// ============================================================
let _uploadInProgress = false;
async function uploadFile() {
    if (_uploadInProgress) return; // prevent double-click
    if (!selectedFile) {
        fileInfo.textContent = 'Please select a file first';
        fileInfo.style.color = '#f56565';
        return;
    }
    _uploadInProgress = true;

    const originalText = uploadBtn.innerHTML;
    uploadBtn.innerHTML = '<span class="loading"><span></span><span></span><span></span></span> Processing...';
    uploadBtn.disabled = true;

    const formData = new FormData();
    formData.append('file', selectedFile);
    if (currentUsername) {
        formData.append('username', currentUsername);
    }

    try {
        const response = await fetch(`${API_BASE_URL}/upload`, {
            method: 'POST',
            body: formData
        });

        const result = await response.json();

        if (response.ok) {
            fileInfo.textContent = `✓ ${selectedFile.name} processed successfully (${result.records_added} records)`;
            fileInfo.style.color = '#48bb78';

            // Set the new dataset as current
            if (result.dataset_id) {
                currentDatasetId = result.dataset_id;
                await loadUserDatasets();
                datasetSelector.value = currentDatasetId;
            }

            addMessage(`Successfully processed ${selectedFile.name} with ${result.records_added} records. You can now ask questions about this data.`, 'bot');
            loadDataSummary();
        } else {
            fileInfo.textContent = `✗ Error: ${result.error}`;
            fileInfo.style.color = '#f56565';
        }
    } catch (error) {
        fileInfo.textContent = '✗ Network error. Is the backend running?';
        fileInfo.style.color = '#f56565';
    } finally {
        uploadBtn.innerHTML = originalText;
        uploadBtn.disabled = false;
        selectedFile = null;
        fileInput.value = '';
        _uploadInProgress = false;
    }
}

// ============================================================
//  DATA SUMMARY (multi-user)
// ============================================================
async function loadDataSummary() {
    try {
        let url = `${API_BASE_URL}/data/summary`;
        if (currentUsername && currentDatasetId) {
            url += `?username=${encodeURIComponent(currentUsername)}&dataset_id=${encodeURIComponent(currentDatasetId)}`;
        }
        const response = await fetch(url);
        const summary = await response.json();

        if (response.ok) {
            updateStatsDisplay(summary);
            renderProductInsights(summary.product_insights);
        }
    } catch (error) {
        console.error('Error loading data summary:', error);
    }
}

// ============================================================
//  STATS DISPLAY
// ============================================================
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

// ============================================================
//  PRODUCT INSIGHTS
// ============================================================
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
            return { border: '#d69e2e', fill: 'rgba(214, 158, 46, 0.20)' };
        }
        if (diff > 0) {
            return { border: '#38a169', fill: 'rgba(56, 161, 105, 0.20)' };
        }
        return { border: '#e53e3e', fill: 'rgba(229, 62, 62, 0.20)' };
    };

    productTrendCharts[canvasId] = new Chart(canvas, {
        type: 'line',
        data: {
            labels,
            datasets: [{
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
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: false },
                tooltip: {
                    enabled: true,
                    callbacks: {
                        title: (tooltipItems) => tooltipItems[0]?.label || '',
                        label: (tooltipItem) => {
                            const value = tooltipItem.raw;
                            if (metricType === 'quantity') return `Units: ${Math.round(value)}`;
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
                            return labels[index] || '';
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

// ============================================================
//  CLEAR DATA
// ============================================================
async function clearData() {
    if (!confirm('Are you sure you want to clear all data?')) return;

    try {
        const response = await fetch(`${API_BASE_URL}/clear`, { method: 'POST' });

        if (response.ok) {
            fileInfo.textContent = 'All data cleared successfully';
            fileInfo.style.color = '#48bb78';

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

            addMessage('All data has been cleared. You can upload new files to start fresh.', 'bot');

            window._predictionsLoaded = false;
            _predictionsCache = null;
            const predContent = document.getElementById('predictionsContent');
            const predEmpty = document.getElementById('predictionsEmpty');
            if (predContent) predContent.style.display = 'none';
            if (predEmpty) {
                predEmpty.style.display = 'block';
                predEmpty.querySelector('h3').textContent = 'No Data Loaded';
                predEmpty.querySelector('p').textContent = 'Upload a CSV/Excel file first, then switch here to see AI-generated predictions.';
            }
        }
    } catch (error) {
        console.error('Error clearing data:', error);
    }
}

// ============================================================
//  CHAT FUNCTIONS (multi-user)
// ============================================================
function askQuestion(question) {
    userInput.value = question;
    sendMessage();
}

async function sendMessage() {
    const query = userInput.value.trim();
    if (!query) return;

    // Hide quick-question chips after first query
    const qq = document.getElementById('quickQuestions');
    if (qq) qq.style.display = 'none';

    addMessage(query, 'user');
    userInput.value = '';
    const loadingId = addLoadingMessage();

    try {
        const body = { query };
        if (currentUsername) body.username = currentUsername;
        if (currentDatasetId) body.dataset_id = currentDatasetId;

        const response = await fetch(`${API_BASE_URL}/query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });

        const result = await response.json();
        removeMessage(loadingId);

        if (response.ok) {
            addMessage(result.response, 'bot');

            if (result.visualizations && Object.keys(result.visualizations).length > 0) {
                displayCharts(result.visualizations);
            }

            if (result.data_summary) {
                updateStatsDisplay(result.data_summary);
                renderProductInsights(result.data_summary.product_insights);
            }
        } else {
            addMessage(`Error: ${result.error}`, 'bot');
        }
    } catch (error) {
        removeMessage(loadingId);
        addMessage('Cannot connect to the backend server. Make sure it is running.', 'bot');
    }
}

function addMessage(content, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender}`;

    const avatarIcon = sender === 'user' ? 'fas fa-user' : 'fas fa-robot';
    const senderName = sender === 'user' ? 'You' : 'Sales Assistant';

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
    if (element) element.remove();
}

function handleKeyPress(e) {
    if (e.key === 'Enter') sendMessage();
}

// ============================================================
//  VISUALIZATIONS (multi-user)
// ============================================================
function displayCharts(charts) {
    if (!charts || Object.keys(charts).length === 0) return;

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

    Object.entries(charts).forEach(([chartName, chartData]) => {
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
    addChartStyles();
}

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

function downloadChart(chartName, chartData) {
    const link = document.createElement('a');
    link.href = 'data:image/png;base64,' + chartData;
    link.download = `sales_chart_${chartName}_${new Date().toISOString().split('T')[0]}.png`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function addChartStyles() {
    if (document.getElementById('chart-styles')) return;

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
        .chart-image:hover { transform: scale(1.02); }
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
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.8);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 1000;
            animation: fadeIn 0.3s;
        }
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
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
        .chart-modal-header h3 { margin: 0; color: #2d3748; }
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
            .charts-container { grid-template-columns: 1fr; }
            .chart-modal-content { width: 95%; max-height: 85vh; }
            .chart-image { height: 160px; }
            .chart-modal-body { padding: 12px; }
            .full-chart-image { max-height: 50vh; }
            .chart-card { padding: 10px; }
            .chart-card h4 { font-size: 13px; }
        }
    `;
    document.head.appendChild(style);
}

async function generateVisualizations() {
    try {
        let url = `${API_BASE_URL}/visualizations`;
        if (currentUsername && currentDatasetId) {
            url += `?username=${encodeURIComponent(currentUsername)}&dataset_id=${encodeURIComponent(currentDatasetId)}`;
        }
        const response = await fetch(url);
        const result = await response.json();

        if (response.ok) {
            addMessage(`Generated ${result.charts ? Object.keys(result.charts).length : 0} visualization(s) from the data.`, 'bot');
            if (result.charts) displayCharts(result.charts);
        } else {
            addMessage(`Error generating charts: ${result.error}`, 'bot');
        }
    } catch (error) {
        addMessage('Error generating visualizations. Make sure backend is running.', 'bot');
    }
}

// ============================================================
//  TAB SWITCHING
// ============================================================
function switchTab(tab) {
    document.getElementById('tabChat').classList.toggle('active', tab === 'chat');
    document.getElementById('tabPredictions').classList.toggle('active', tab === 'predictions');
    document.getElementById('chatTab').classList.toggle('active', tab === 'chat');
    document.getElementById('predictionsTab').classList.toggle('active', tab === 'predictions');

    if (tab === 'predictions' && !window._predictionsLoaded) {
        const totalRecords = document.getElementById('totalRecords');
        if (totalRecords && parseInt(totalRecords.textContent) > 0) {
            loadPredictions();
        }
    }
}

// ============================================================
//  PREDICTIONS (multi-user)
// ============================================================
let _predictionsCache = null;

async function loadPredictions() {
    const loadingEl = document.getElementById('predictionsLoading');
    const emptyEl = document.getElementById('predictionsEmpty');
    const contentEl = document.getElementById('predictionsContent');
    const refreshBtn = document.getElementById('refreshPredictionsBtn');

    loadingEl.style.display = 'flex';
    emptyEl.style.display = 'none';
    contentEl.style.display = 'none';
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = '<i class="fas fa-sync-alt fa-spin"></i> Generating...';

    try {
        let url = `${API_BASE_URL}/predictions`;
        if (currentUsername && currentDatasetId) {
            url += `?username=${encodeURIComponent(currentUsername)}&dataset_id=${encodeURIComponent(currentDatasetId)}`;
        }
        const response = await fetch(url);
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

        const pdfBtn = document.getElementById('downloadPdfBtn');
        if (pdfBtn) pdfBtn.style.display = 'flex';

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

// ============================================================
//  PDF DOWNLOAD
// ============================================================
function downloadPredictionsPDF() {
    const content = document.getElementById('predictionsContent');
    if (!content || content.children.length === 0) {
        alert('No predictions to download. Generate predictions first.');
        return;
    }

    const btn = document.getElementById('downloadPdfBtn');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating PDF...';

    const pdfContainer = document.createElement('div');
    pdfContainer.style.cssText = 'padding: 30px; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif; color: #2d3748; background: white;';

    const title = document.createElement('div');
    title.innerHTML = `
        <div style="text-align:center; margin-bottom:24px; padding-bottom:16px; border-bottom:2px solid #4a6cf7;">
            <h1 style="font-size:22px; color:#2d3748; margin:0 0 6px 0;">Sales Predictions & Insights</h1>
            <p style="font-size:12px; color:#718096; margin:0;">Generated on ${new Date().toLocaleDateString('en-IN', { day:'numeric', month:'long', year:'numeric' })} &bull; AI Sales Analytics &bull; ${currentUsername}</p>
        </div>
    `;
    pdfContainer.appendChild(title);

    const sectionColors = {
        'forecast': '#4a6cf7',
        'products': '#48bb78',
        'regions': '#ed8936',
        'alternatives': '#9f7aea',
        'improvements': '#38b2ac'
    };

    content.querySelectorAll('.pred-section').forEach(section => {
        const sectionClone = document.createElement('div');
        sectionClone.style.cssText = 'margin-bottom:20px; page-break-inside:avoid;';

        const titleEl = section.querySelector('.pred-section-title');
        const cssClass = Array.from(section.classList).find(c => c !== 'pred-section') || 'forecast';
        const color = sectionColors[cssClass] || '#4a6cf7';

        const sectionTitle = document.createElement('div');
        sectionTitle.style.cssText = `font-size:16px; font-weight:700; color:${color}; margin-bottom:10px; padding-bottom:4px; border-bottom:2px solid ${color}30;`;
        sectionTitle.textContent = titleEl ? titleEl.textContent.trim() : 'Section';
        sectionClone.appendChild(sectionTitle);

        section.querySelectorAll('.pred-item').forEach(item => {
            const itemDiv = document.createElement('div');
            itemDiv.style.cssText = `background:#f8fafc; border-left:3px solid ${color}; border-radius:6px; padding:10px 14px; margin-bottom:8px;`;

            const labelText = item.querySelector('.pred-item-label')?.textContent || '';
            const value = item.querySelector('.pred-item-value')?.textContent || '';
            const detail = item.querySelector('.pred-item-detail')?.textContent || '';

            const badges = [];
            item.querySelectorAll('.pred-badge').forEach(b => badges.push(b.textContent.trim()));
            const badgeText = badges.length > 0
                ? `<div style="margin-top:6px;font-size:10px;color:#718096;">${badges.join(' &bull; ')}</div>`
                : '';

            itemDiv.innerHTML = `
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
                    <span style="font-size:13px;font-weight:600;color:#2d3748;">${escapeHTML(labelText)}</span>
                    ${value ? `<span style="font-size:13px;font-weight:700;color:${color};white-space:nowrap;">${escapeHTML(value)}</span>` : ''}
                </div>
                <div style="font-size:12px;color:#4a5568;line-height:1.5;">${escapeHTML(detail)}</div>
                ${badgeText}
            `;
            sectionClone.appendChild(itemDiv);
        });

        pdfContainer.appendChild(sectionClone);
    });

    const footer = document.createElement('div');
    footer.innerHTML = `<div style="text-align:center;font-size:10px;color:#a0aec0;margin-top:20px;padding-top:10px;border-top:1px solid #e2e8f0;">&copy; Team Abscond 2026 &bull; AI Sales Analytics</div>`;
    pdfContainer.appendChild(footer);

    const opt = {
        margin: [10, 10, 10, 10],
        filename: `Sales_Predictions_${new Date().toISOString().slice(0, 10)}.pdf`,
        image: { type: 'jpeg', quality: 0.98 },
        html2canvas: { scale: 2, useCORS: true },
        jsPDF: { unit: 'mm', format: 'a4', orientation: 'portrait' },
        pagebreak: { mode: ['avoid-all', 'css', 'legacy'] }
    };

    html2pdf().set(opt).from(pdfContainer).save().then(() => {
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-file-pdf"></i> Download PDF';
    }).catch(err => {
        console.error('PDF generation error:', err);
        btn.disabled = false;
        btn.innerHTML = '<i class="fas fa-file-pdf"></i> Download PDF';
        alert('Failed to generate PDF. Please try again.');
    });
}
