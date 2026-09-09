// Bird Cam Control JavaScript

// State
let isRecording = false;
let isLiveMode = false;
let liveInterval = null;

// DOM Elements
const photoBtn = document.getElementById('photoBtn');
const recordBtn = document.getElementById('recordBtn');
const liveBtn = document.getElementById('liveBtn');
const refreshBtn = document.getElementById('refreshBtn');
const status = document.getElementById('status');
const photoCount = document.getElementById('photoCount');
const videoCount = document.getElementById('videoCount');
const fileList = document.getElementById('fileList');
const motionCount = document.getElementById('motionCount');
const previewImage = document.getElementById('previewImage');
const noImageMessage = document.getElementById('noImageMessage');
const liveIndicator = document.getElementById('liveIndicator');
const previewOverlay = document.getElementById('previewOverlay');

// Event Listeners
photoBtn.addEventListener('click', takePhoto);
recordBtn.addEventListener('click', toggleRecording);
liveBtn.addEventListener('click', toggleLiveMode);
refreshBtn.addEventListener('click', refreshFiles);

// Functions
function updateStatus(message, type = 'normal') {
    const statusBar = document.getElementById('status');
    const statusText = statusBar.querySelector('.status-text');
    statusText.textContent = message;
    statusBar.className = 'status-bar';
    
    if (type === 'success') {
        statusBar.classList.add('success');
    } else if (type === 'error') {
        statusBar.classList.add('error');
    } else if (type === 'warning') {
        statusBar.classList.add('warning');
    }
    
    // Clear status after 5 seconds
    if (type !== 'normal') {
        setTimeout(() => {
            statusBar.className = 'status-bar';
            statusText.textContent = 'Ready';
        }, 5000);
    }
}

async function loadLatestImage() {
    try {
        const response = await fetch('/api/latest_image');
        const data = await response.json();
        
        if (data.success) {
            previewImage.src = data.url;
            previewImage.classList.add('active');
            noImageMessage.style.display = 'none';
        }
    } catch (error) {
        console.error('Error loading latest image:', error);
    }
}

async function takePhoto() {
    photoBtn.disabled = true;
    updateStatus('Taking photo...', 'warning');
    previewOverlay.classList.add('active');
    
    try {
        const response = await fetch('/api/take_photo', { method: 'POST' });
        const data = await response.json();
        
        if (data.success) {
            updateStatus(data.message, 'success');
            updateCounts();
            refreshFiles();
            // Load the new photo
            setTimeout(() => {
                previewImage.src = `/files/${data.filename}`;
                previewImage.classList.add('active');
                noImageMessage.style.display = 'none';
                previewOverlay.classList.remove('active');
            }, 500);
        } else {
            updateStatus(data.message, 'error');
            previewOverlay.classList.remove('active');
        }
    } catch (error) {
        updateStatus('Failed to take photo', 'error');
        console.error('Error:', error);
        previewOverlay.classList.remove('active');
    } finally {
        photoBtn.disabled = false;
    }
}

async function toggleLiveMode() {
    if (!isLiveMode) {
        // Start live mode
        isLiveMode = true;
        liveBtn.classList.add('active');
        liveBtn.innerHTML = '<span class="btn-icon">⏹️</span><span class="btn-text">Stop Live</span>';
        liveIndicator.classList.add('active');
        updateStatus('Live mode active', 'success');
        
        // Disable other buttons during live mode
        photoBtn.disabled = true;
        recordBtn.disabled = true;
        
        // Stream MJPEG straight into the <img> — no polling
        previewImage.src = '/api/stream';
        previewImage.classList.add('active');
        noImageMessage.style.display = 'none';
    } else {
        // Stop live mode
        isLiveMode = false;
        liveBtn.classList.remove('active');
        liveBtn.innerHTML = '<span class="btn-icon">👁️</span><span class="btn-text">Live Mode</span>';
        liveIndicator.classList.remove('active');
        updateStatus('Live mode stopped', 'warning');
        
        // Re-enable buttons
        photoBtn.disabled = false;
        recordBtn.disabled = false;
        
        // Stop the MJPEG stream (closes the server-side connection)
        previewImage.src = '';

        // Stop the live mode animation on the Sense HAT
        try {
            await fetch('/api/stop_live_mode', { method: 'POST' });
        } catch (error) {
            console.error('Error stopping live mode:', error);
        }
        
        // Reload the latest saved image
        loadLatestImage();
    }
}


async function toggleRecording() {
    recordBtn.disabled = true;
    
    if (!isRecording) {
        try {
            const response = await fetch('/api/start_recording', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                isRecording = true;
                recordBtn.innerHTML = '<span class="btn-icon">⏹️</span><span class="btn-text">Stop Recording</span>';
                recordBtn.classList.add('recording');
                updateStatus('Recording...', 'error');
            } else {
                updateStatus(data.message, 'error');
            }
        } catch (error) {
            updateStatus('Failed to start recording', 'error');
            console.error('Error:', error);
        }
    } else {
        updateStatus('Stopping recording...', 'warning');
        try {
            const response = await fetch('/api/stop_recording', { method: 'POST' });
            const data = await response.json();
            
            isRecording = false;
            recordBtn.innerHTML = '<span class="btn-icon">🎥</span><span class="btn-text">Start Recording</span>';
            recordBtn.classList.remove('recording');
            
            if (data.success) {
                updateStatus(data.message, 'success');
                updateCounts();
                refreshFiles();
            } else {
                updateStatus(data.message, 'error');
            }
        } catch (error) {
            updateStatus('Failed to stop recording', 'error');
            console.error('Error:', error);
        }
    }
    
    recordBtn.disabled = false;
}

async function refreshFiles() {
    try {
        const response = await fetch('/api/list_files');
        const data = await response.json();
        
        if (data.success) {
            if (data.files.length === 0) {
                fileList.innerHTML = '<div class="empty">No captures yet. Take a photo or record a video!</div>';
            } else {
                fileList.innerHTML = data.files.map(file => {
                    const isPhoto = file.endsWith('.jpg');
                    const type = isPhoto ? 'photo' : 'video';
                    const icon = isPhoto ? '📸' : '🎥';
                    
                    return `
                        <div class="file-item">
                            <a href="/files/${file}" target="_blank">${icon} ${file}</a>
                            <span class="file-type ${type}">${type}</span>
                        </div>
                    `;
                }).join('');
            }
        }
    } catch (error) {
        console.error('Error loading files:', error);
        fileList.innerHTML = '<div class="error">Failed to load files</div>';
    }
}

async function updateCounts() {
    try {
        const response = await fetch('/api/counts');
        const data = await response.json();
        
        photoCount.textContent = data.photo_count;
        videoCount.textContent = data.video_count;
        motionCount.textContent = data.motion_count;
    } catch (error) {
        console.error('Error updating counts:', error);
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    // First, check if we have any existing images
    const latestResponse = await fetch('/api/latest_image');
    const latestData = await latestResponse.json();
    
    if (!latestData.success) {
        // No images exist, take a new photo immediately
        updateStatus('Taking initial photo...', 'warning');
        await takePhoto();
    } else {
        // Load the existing latest image
        loadLatestImage();
    }
    
    // Then load files and counts
    await refreshFiles();
    await updateCounts();
    
    // Update status
    updateStatus('Ready', 'normal');
    
    // Auto-refresh files every 30 seconds
    setInterval(refreshFiles, 30000);
});