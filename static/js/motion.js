// Motion detection functionality for Bird Cam

// State
let isMotionActive = false;
let motionInterval = null;
let lastCaptureTime = 0;

// Functions for motion detection mode
async function toggleMotionMode() {
    const motionBtn = document.getElementById('motionBtn');
    
    if (!isMotionActive) {
        // Start motion detection
        motionBtn.disabled = true;
        
        try {
            const response = await fetch('/api/start_motion', { method: 'POST' });
            const data = await response.json();
            
            if (data.success) {
                isMotionActive = true;
                motionBtn.classList.add('active');
                motionBtn.innerHTML = '<span class="btn-icon">⏹️</span><span class="btn-text">Stop Motion</span>';
                updateStatus('Motion detection active', 'success');
                
                // Update motion indicator
                const motionIndicator = document.getElementById('motionIndicator');
                if (motionIndicator) {
                    motionIndicator.classList.add('active');
                }
                
                // Start polling for new motion captures
                startMotionPolling();
            } else {
                updateStatus(data.message || 'Failed to start motion detection', 'error');
            }
        } catch (error) {
            console.error('Error starting motion detection:', error);
            updateStatus('Error starting motion detection', 'error');
        } finally {
            motionBtn.disabled = false;
        }
    } else {
        // Stop motion detection
        motionBtn.disabled = true;
        
        try {
            const response = await fetch('/api/stop_motion', { method: 'POST' });
            const data = await response.json();
            
            isMotionActive = false;
            motionBtn.classList.remove('active');
            motionBtn.innerHTML = '<span class="btn-icon">👁️</span><span class="btn-text">Motion Mode</span>';
            updateStatus('Motion detection stopped', 'warning');
            
            // Update motion indicator
            const motionIndicator = document.getElementById('motionIndicator');
            if (motionIndicator) {
                motionIndicator.classList.remove('active');
            }
            
            // Stop polling
            if (motionInterval) {
                clearInterval(motionInterval);
                motionInterval = null;
            }
        } catch (error) {
            console.error('Error stopping motion detection:', error);
            updateStatus('Error stopping motion detection', 'error');
        } finally {
            motionBtn.disabled = false;
        }
    }
}

function startMotionPolling() {
    // Check for new motion captures every 5 seconds
    if (motionInterval) {
        clearInterval(motionInterval);
    }
    
    // Poll immediately
    checkForNewCaptures();
    
    // Then set up interval
    motionInterval = setInterval(checkForNewCaptures, 5000);
}

async function checkForNewCaptures() {
    if (!isMotionActive) return;
    
    try {
        const response = await fetch('/api/motion_status');
        const data = await response.json();
        
        if (data.success) {
            // If there's a new capture and it's newer than our last known capture
            if (data.last_capture && data.last_capture_time > lastCaptureTime) {
                lastCaptureTime = data.last_capture_time;
                
                // Show notification
                updateStatus(`Motion detected! Captured: ${data.last_capture}`, 'warning');
                
                // Refresh the file list
                refreshFiles();
                
                // Update the preview with the new capture
                if (data.last_capture.endsWith('.jpg')) {
                    previewImage.src = `/files/${data.last_capture}`;
                    previewImage.classList.add('active');
                    noImageMessage.style.display = 'none';
                }
                
                // Update counts
                updateCounts();
            }
        }
    } catch (error) {
        console.error('Error checking motion status:', error);
    }
}

// Motion settings dialog functionality
function openMotionSettings() {
    // First, get current settings
    fetch('/api/motion_settings')
        .then(response => response.json())
        .then(settings => {
            if (settings.success) {
                // Update the form with current values
                document.getElementById('motion-threshold').value = settings.threshold;
                document.getElementById('motion-min-area').value = settings.min_area;
                document.getElementById('motion-cooldown').value = settings.cooldown;
                document.getElementById('motion-consecutive-frames').value = settings.consecutive_frames;
                
                // Show the dialog
                document.getElementById('motionSettingsDialog').classList.add('active');
            } else {
                updateStatus('Failed to get motion settings', 'error');
            }
        })
        .catch(error => {
            console.error('Error getting motion settings:', error);
            updateStatus('Error retrieving motion settings', 'error');
        });
}

function closeMotionSettings() {
    document.getElementById('motionSettingsDialog').classList.remove('active');
}

async function saveMotionSettings() {
    const settings = {
        threshold: document.getElementById('motion-threshold').value,
        min_area: document.getElementById('motion-min-area').value,
        cooldown: document.getElementById('motion-cooldown').value,
        consecutive_frames: document.getElementById('motion-consecutive-frames').value
    };
    
    try {
        const response = await fetch('/api/motion_settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });
        
        const data = await response.json();
        
        if (data.success) {
            updateStatus('Motion settings saved', 'success');
            closeMotionSettings();
        } else {
            updateStatus(data.message || 'Failed to save settings', 'error');
        }
    } catch (error) {
        console.error('Error saving motion settings:', error);
        updateStatus('Error saving motion settings', 'error');
    }
}

// Initialize motion mode
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners if the elements exist
    const motionBtn = document.getElementById('motionBtn');
    if (motionBtn) {
        motionBtn.addEventListener('click', toggleMotionMode);
    }
    
    const motionSettingsBtn = document.getElementById('motionSettingsBtn');
    if (motionSettingsBtn) {
        motionSettingsBtn.addEventListener('click', openMotionSettings);
    }
    
    const saveSettingsBtn = document.getElementById('saveMotionSettingsBtn');
    if (saveSettingsBtn) {
        saveSettingsBtn.addEventListener('click', saveMotionSettings);
    }
    
    const closeSettingsBtn = document.getElementById('closeMotionSettingsBtn');
    if (closeSettingsBtn) {
        closeSettingsBtn.addEventListener('click', closeMotionSettings);
    }

    const cancelSettingsBtn = document.getElementById('cancelMotionSettingsBtn');
    if (cancelSettingsBtn) {
        cancelSettingsBtn.addEventListener('click', closeMotionSettings);
    }
    
    // Check if motion mode is active on load
    fetch('/api/motion_status')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.is_active) {
                isMotionActive = true;
                if (motionBtn) {
                    motionBtn.classList.add('active');
                    motionBtn.innerHTML = '<span class="btn-icon">⏹️</span><span class="btn-text">Stop Motion</span>';
                }
                
                // Update motion indicator
                const motionIndicator = document.getElementById('motionIndicator');
                if (motionIndicator) {
                    motionIndicator.classList.add('active');
                }
                
                // Start polling for new captures
                startMotionPolling();
            }
        })
        .catch(error => {
            console.error('Error checking initial motion status:', error);
        });
});