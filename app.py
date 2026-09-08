#!/usr/bin/env python3
from flask import Flask, render_template, jsonify, send_from_directory, request
import subprocess
from datetime import datetime
import time
import os
import signal
import base64
import threading
import logging
from logging.handlers import RotatingFileHandler

# Import our Sense HAT and Motion utilities
from utilities import sensehat_utils
from utilities import motion_utils

app = Flask(__name__)

# Set up logging
if not os.path.exists('logs'):
    os.makedirs('logs')

# Create a rotating file handler (max 10MB per file, keep 10 backups)
file_handler = RotatingFileHandler('logs/birdcam.log', maxBytes=10485760, backupCount=10)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)

# Set up the logger
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Bird Cam startup')

# Also log to console for systemd journal
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
app.logger.addHandler(console_handler)

# Global variables
recording = False
video_process = None
video_filename = None
photo_count = 0
video_count = 0
last_random_display = time.time()
display_thread_running = True
RANDOM_DISPLAY_INTERVAL = 300  # 5 minutes in seconds

# Motion detection globals
motion_mode_active = False
last_motion_capture = None
last_motion_time = 0

def create_images_folder():
    """Create media folder if it doesn't exist"""
    folder_path = 'media'
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path

def display_loop():
    """Background thread for always-on display"""
    global display_thread_running, last_random_display
    
    while display_thread_running:
        try:
            # If not recording or in photo countdown, show the always-on display
            if not recording and not motion_mode_active:
                # Check if it's time for a random display
                if time.time() - last_random_display > RANDOM_DISPLAY_INTERVAL:
                    sensehat_utils.show_random_display()
                    last_random_display = time.time()
                
                # Always show the temp/time display
                sensehat_utils.always_on_display()
            
            # Sleep for a bit before updating
            time.sleep(5)
            
        except Exception as e:
            print(f"Error in display loop: {e}")
            time.sleep(5)

def on_motion_detected():
    """Callback function when motion is detected"""
    global last_motion_capture, last_motion_time
    
    app.logger.info("Motion detected! Capturing...")
    
    # Decide whether to take a photo or video (alternating or based on settings)
    # For this example, we'll just take a photo
    filename = motion_utils.capture_motion_photo()
    
    if filename:
        # Update last motion capture info
        last_motion_capture = os.path.basename(filename)
        last_motion_time = time.time()
        app.logger.info(f"Motion capture saved: {last_motion_capture}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/take_photo', methods=['POST'])
def take_photo():
    global photo_count
    
    app.logger.info("Taking photo...")
    
    try:
        folder_path = create_images_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{folder_path}/{timestamp}.jpg"
        
        # Start countdown animation
        sensehat_utils.photo_countdown()
        
        # Take photo with libcamera-still
        subprocess.run([
            'libcamera-still',
            '-o', filename,
            '--nopreview',
            '--immediate',
            '--timeout', '1'
        ], check=True, capture_output=True)
        
        # Show success
        sensehat_utils.show_photo_success()
        
        photo_count += 1
        app.logger.info(f"Photo saved successfully: {filename}")
        return jsonify({
            'success': True, 
            'message': f'Photo #{photo_count} saved!',
            'filename': os.path.basename(filename)
        })
    
    except Exception as e:
        app.logger.error(f"Error taking photo: {e}")
        sensehat_utils.show_photo_error()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/start_recording', methods=['POST'])
def start_recording():
    global recording, video_process, video_filename, video_count
    
    if recording:
        return jsonify({'success': False, 'message': 'Already recording'})
    
    app.logger.info("Starting video recording...")
    
    try:
        folder_path = create_images_folder()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_filename = f"{folder_path}/{timestamp}_temp.h264"
        video_filename = f"{folder_path}/{timestamp}.mp4"
        
        # Show recording indicator
        sensehat_utils.show_recording_active()
        
        video_process = subprocess.Popen([
            'libcamera-vid',
            '-o', temp_filename,
            '--nopreview',
            '-t', '0',
            '--width', '1920',
            '--height', '1080'
        ])
        
        recording = True
        video_count += 1
        app.logger.info(f"Recording started: {temp_filename}")
        return jsonify({'success': True, 'message': 'Recording started'})
    
    except Exception as e:
        app.logger.error(f"Error starting recording: {e}")
        sensehat_utils.show_recording_error()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/stop_recording', methods=['POST'])
def stop_recording():
    global recording, video_process, video_filename
    
    if not recording:
        return jsonify({'success': False, 'message': 'Not recording'})
    
    try:
        # Stop recording
        video_process.terminate()
        video_process.wait()
        recording = False
        
        # Show converting indicator
        sensehat_utils.show_recording_converting()
        
        # Get the temp filename
        temp_file = video_filename.replace('.mp4', '_temp.h264')
        
        # Convert to MP4
        result = subprocess.run([
            'ffmpeg',
            '-i', temp_file,
            '-c:v', 'copy',
            video_filename,
            '-y'
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            os.remove(temp_file)
            sensehat_utils.show_recording_success()
            return jsonify({
                'success': True, 
                'message': f'Video #{video_count} saved!',
                'filename': os.path.basename(video_filename)
            })
        else:
            # Fallback to h264
            final_h264 = temp_file.replace('_temp.h264', '.h264')
            os.rename(temp_file, final_h264)
            sensehat_utils.show_recording_warning()
            return jsonify({
                'success': True,
                'message': f'Video #{video_count} saved (H264)',
                'filename': os.path.basename(final_h264)
            })
    
    except Exception as e:
        sensehat_utils.clear_display()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/start_motion', methods=['POST'])
def start_motion_detection():
    """Start motion detection mode"""
    global motion_mode_active
    
    if motion_mode_active:
        return jsonify({'success': False, 'message': 'Motion detection already active'})
    
    app.logger.info("Starting motion detection...")
    
    try:
        # Show motion mode on Sense HAT
        sensehat_utils.show_recording_active()  # Reusing recording animation
        
        # Start motion detection
        if motion_utils.start_motion_detection(callback_on_motion=on_motion_detected):
            motion_mode_active = True
            app.logger.info("Motion detection started successfully")
            return jsonify({'success': True, 'message': 'Motion detection started'})
        else:
            sensehat_utils.show_recording_error()
            return jsonify({'success': False, 'message': 'Failed to start motion detection'})
    
    except Exception as e:
        app.logger.error(f"Error starting motion detection: {e}")
        sensehat_utils.show_recording_error()
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/stop_motion', methods=['POST'])
def stop_motion_detection():
    """Stop motion detection mode"""
    global motion_mode_active
    
    if not motion_mode_active:
        return jsonify({'success': False, 'message': 'Motion detection not active'})
    
    app.logger.info("Stopping motion detection...")
    
    try:
        # Stop motion detection
        if motion_utils.stop_motion_detection():
            motion_mode_active = False
            app.logger.info("Motion detection stopped successfully")
            
            # Clear Sense HAT
            sensehat_utils.clear_display()
            
            return jsonify({'success': True, 'message': 'Motion detection stopped'})
        else:
            return jsonify({'success': False, 'message': 'Failed to stop motion detection'})
    
    except Exception as e:
        app.logger.error(f"Error stopping motion detection: {e}")
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/motion_status')
def get_motion_status():
    """Get current motion detection status"""
    global motion_mode_active, last_motion_capture, last_motion_time
    
    return jsonify({
        'success': True,
        'is_active': motion_mode_active,
        'last_capture': last_motion_capture,
        'last_capture_time': last_motion_time
    })

@app.route('/api/motion_settings', methods=['GET', 'POST'])
def motion_settings():
    """Get or update motion detection settings"""
    if request.method == 'GET':
        # Get current settings
        settings = motion_utils.get_motion_settings()
        return jsonify({'success': True, **settings})
    else:
        # Update settings
        try:
            data = request.json
            settings = motion_utils.update_motion_settings(
                threshold=data.get('threshold'),
                min_area=data.get('min_area'),
                cooldown=data.get('cooldown'),
                consecutive_frames=data.get('consecutive_frames')
            )
            return jsonify({'success': True, **settings})
        except Exception as e:
            app.logger.error(f"Error updating motion settings: {e}")
            return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/api/list_files')
def list_files():
    try:
        folder_path = 'media'
        if os.path.exists(folder_path):
            files = sorted([f for f in os.listdir(folder_path) 
                          if f.endswith(('.jpg', '.mp4', '.h264'))], 
                         reverse=True)[:30]  # Last 30 files
        else:
            files = []
        return jsonify({'success': True, 'files': files})
    except Exception as e:
        return jsonify({'success': False, 'files': [], 'error': str(e)})

@app.route('/api/counts')
def get_counts():
    # Count actual files in the directory
    try:
        folder_path = 'media'
        if os.path.exists(folder_path):
            files = os.listdir(folder_path)
            photo_count = len([f for f in files if f.endswith('.jpg')])
            video_count = len([f for f in files if f.endswith(('.mp4', '.h264'))])
            motion_count = len([f for f in files if '_motion' in f])
        else:
            photo_count = 0
            video_count = 0
            motion_count = 0
    except:
        photo_count = 0
        video_count = 0
        motion_count = 0
    
    return jsonify({
        'photo_count': photo_count,
        'video_count': video_count,
        'motion_count': motion_count
    })

@app.route('/api/latest_image')
def get_latest_image():
    try:
        folder_path = 'media'
        if os.path.exists(folder_path):
            # Get all image files
            images = [f for f in os.listdir(folder_path) if f.endswith('.jpg')]
            if images:
                # Sort by modification time and get the latest
                images.sort(key=lambda x: os.path.getmtime(os.path.join(folder_path, x)), reverse=True)
                return jsonify({
                    'success': True,
                    'image': images[0],
                    'url': f'/files/{images[0]}'
                })
        return jsonify({'success': False, 'message': 'No images found'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/live_snapshot')
def live_snapshot():
    """Take a snapshot for live mode without saving"""
    
    try:
        # Ensure live mode animation is running
        sensehat_utils.start_live_mode()
        
        # Take a temporary snapshot
        temp_file = '/tmp/live_snapshot.jpg'
        subprocess.run([
            'libcamera-still',
            '-o', temp_file,
            '--nopreview',
            '--immediate',
            '--timeout', '1',
            '--width', '640',
            '--height', '480'
        ], check=True, capture_output=True)
        
        # Read and return the image
        with open(temp_file, 'rb') as f:
            image_data = f.read()
        
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        return jsonify({
            'success': True,
            'image': f'data:image/jpeg;base64,{image_base64}'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/stop_live_mode', methods=['POST'])
def stop_live_mode():
    """Stop the live mode animation"""
    
    try:
        sensehat_utils.stop_live_mode()
        return jsonify({'success': True, 'message': 'Live mode stopped'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/test_countdown', methods=['POST'])
def test_countdown():
    """Test the countdown animation without taking a photo"""
    
    try:
        sensehat_utils.photo_countdown()
        sensehat_utils.clear_display()
        return jsonify({'success': True, 'message': 'Countdown test complete'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/force_random_display', methods=['POST'])
def force_random_display():
    """Force a random display to show immediately"""
    global last_random_display
    try:
        sensehat_utils.show_random_display()
        last_random_display = time.time()
        return jsonify({'success': True, 'message': 'Random display shown'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/files/<path:filename>')
def serve_file(filename):
    return send_from_directory('media', filename)

def signal_handler(sig, frame):
    global display_thread_running, motion_mode_active
    app.logger.info("Shutting down Bird Cam...")
    print("\nShutting down...")
    
    # Stop motion detection if active
    if motion_mode_active:
        motion_utils.stop_motion_detection()
    
    # Stop display thread
    display_thread_running = False
    sensehat_utils.clear_display()
    exit(0)

# Initialize everything whether running directly or as a module
def initialize_app():
    """Initialize the application"""
    global motion_mode_active
    
    # Clear sense hat
    sensehat_utils.clear_display()
    
    # Create folder
    create_images_folder()
    
    # Show ready message
    sensehat_utils.show_startup_message()
    
    # Start always-on display thread
    display_thread = threading.Thread(target=display_loop, daemon=True)
    display_thread.start()
    app.logger.info("Display thread started successfully")
    
    # Start motion detection by default if not running through web interface
    if __name__ != '__main__':
        app.logger.info("Starting motion detection by default...")
        try:
            if motion_utils.start_motion_detection(callback_on_motion=on_motion_detected):
                motion_mode_active = True
                app.logger.info("Default motion detection started successfully")
        except Exception as e:
            app.logger.error(f"Error starting default motion detection: {e}")
    
    # Get IP address
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        app.logger.info(f"Bird Cam Web Interface Ready at http://{ip}:5000")
        print(f"\n🦜 Bird Cam Web Interface Ready! 🦜")
        print(f"Access at: http://{ip}:5000")
        print(f"Temperature/time display is always on")
        print(f"Random displays will show every {RANDOM_DISPLAY_INTERVAL // 60} minutes")
        print(f"Logs are being written to: logs/birdcam.log")
        
        # Print motion detection status
        if motion_mode_active:
            print(f"Motion detection is ACTIVE")
        else:
            print(f"Motion detection is inactive")
    except Exception as e:
        app.logger.error(f"Error getting IP address: {e}")
        print("\nBird Cam Web Interface starting...")
        print("Access at: http://[YOUR_PI_IP]:5000")
        print(f"Temperature/time display is always on")
        print(f"Random displays will show every {RANDOM_DISPLAY_INTERVAL // 60} minutes")
        print(f"Logs are being written to: logs/birdcam.log")
    
    print("Press Ctrl+C to stop\n")

# Initialize the app
initialize_app()

if __name__ == '__main__':
    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run Flask app
    app.logger.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=5000, debug=False)