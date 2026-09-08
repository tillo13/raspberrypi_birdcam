#!/usr/bin/env python3
"""
Motion detection utilities for Bird Cam
Uses libcamera-still to capture frames and OpenCV for motion detection
Optimized for reliability and sensitivity
"""

import cv2
import numpy as np
import time
import os
import logging
import threading
import subprocess
import tempfile
from datetime import datetime

# Set up logging
logger = logging.getLogger('motion_utils')
logger.setLevel(logging.INFO)

# Add file handler for detailed debugging
if not os.path.exists('logs'):
    os.makedirs('logs')
    
motion_debug_log = logging.FileHandler('logs/motion_debug.log')
motion_debug_log.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
motion_debug_log.setLevel(logging.DEBUG)
logger.addHandler(motion_debug_log)

# Motion detection settings - optimized for better sensitivity
MOTION_THRESHOLD = 15       # Threshold for motion detection (lower = more sensitive)
MIN_MOTION_AREA = 200       # Minimum area of motion to trigger (in pixels)
MOTION_COOLDOWN = 2.0       # Seconds to wait between motion events
CONSECUTIVE_FRAMES_NEEDED = 1  # Number of consecutive frames with motion to trigger
FRAME_INTERVAL = 0.7        # Time in seconds between frame captures

# Global variables
motion_active = False
motion_thread = None
last_motion_time = 0
consecutive_frames_with_motion = 0
camera_busy = False  # Flag to track if camera is currently in use

def start_motion_detection(callback_on_motion=None):
    """Start motion detection in a separate thread"""
    global motion_active, motion_thread
    
    if motion_thread is not None and motion_thread.is_alive():
        logger.info("Motion detection already running")
        return False
    
    logger.info("Setting up motion detection thread")
    motion_active = True
    motion_thread = threading.Thread(
        target=_motion_detection_loop,
        args=(callback_on_motion,),
        daemon=True
    )
    motion_thread.start()
    logger.info("Started motion detection thread")
    return True

def stop_motion_detection():
    """Stop motion detection thread"""
    global motion_active
    
    if motion_active:
        logger.info("Stopping motion detection")
        motion_active = False
        # Give thread time to clean up
        time.sleep(0.5)
        return True
    else:
        logger.info("Motion detection already stopped")
        return False

def _capture_frame():
    """Capture a single frame using libcamera-still"""
    global camera_busy
    
    # If camera is busy, wait for it to be free
    if camera_busy:
        logger.debug("Camera busy, waiting before capturing frame")
        time.sleep(1)
    
    # Create a temporary file for the image
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
        temp_filename = temp_file.name
    
    try:
        # Mark camera as busy
        camera_busy = True
        
        # Capture a low-resolution image for faster processing
        subprocess.run([
            'libcamera-still',
            '-o', temp_filename,
            '--nopreview',
            '--immediate',
            '--timeout', '1',
            '--width', '640',
            '--height', '480'
        ], check=True, capture_output=True, timeout=3)  # Increased timeout for reliability
        
        # Read the image with OpenCV
        frame = cv2.imread(temp_filename)
        
        # Remove temporary file
        os.unlink(temp_filename)
        
        # Mark camera as free
        camera_busy = False
        
        if frame is None:
            logger.error("Failed to read captured frame")
            return None
            
        return frame
        
    except subprocess.TimeoutExpired:
        logger.error("Timeout capturing frame with libcamera-still")
        if os.path.exists(temp_filename):
            os.unlink(temp_filename)
        camera_busy = False  # Reset busy flag
        return None
    except Exception as e:
        logger.error(f"Error capturing frame: {e}")
        if os.path.exists(temp_filename):
            os.unlink(temp_filename)
        camera_busy = False  # Reset busy flag
        return None

def _motion_detection_loop(callback_on_motion=None):
    """Main motion detection loop (runs in a thread)"""
    global motion_active, last_motion_time, consecutive_frames_with_motion
    
    logger.info("Initializing motion detection")
    logger.info(f"Motion settings: threshold={MOTION_THRESHOLD}, min_area={MIN_MOTION_AREA}, " 
                f"consecutive_frames={CONSECUTIVE_FRAMES_NEEDED}, cooldown={MOTION_COOLDOWN}, "
                f"frame_interval={FRAME_INTERVAL}")
    
    # Track consecutive failures to help with recovery
    consecutive_failures = 0
    
    try:
        # Capture initial frame with retry logic
        previous_frame = None
        for _ in range(3):  # Try up to 3 times
            previous_frame = _capture_frame()
            if previous_frame is not None:
                break
            time.sleep(1)  # Wait between retries
            
        if previous_frame is None:
            logger.error("Failed to capture initial frame after multiple attempts")
            motion_active = False
            return
        
        # Convert to grayscale and blur for better motion detection
        previous_frame = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
        previous_frame = cv2.GaussianBlur(previous_frame, (21, 21), 0)
        
        logger.info("Motion detection running and active")
        frame_count = 0
        
        # Main detection loop
        while motion_active:
            # Wait before capturing next frame
            time.sleep(FRAME_INTERVAL)
            
            # Capture current frame
            current_frame_color = _capture_frame()
            
            # Handle frame capture failure with recovery logic
            if current_frame_color is None:
                consecutive_failures += 1
                logger.error(f"Failed to capture frame in detection loop (failure #{consecutive_failures})")
                
                if consecutive_failures >= 3:
                    # After 3 consecutive failures, try to reset by getting a new reference frame
                    logger.warning("Multiple consecutive failures, attempting recovery")
                    time.sleep(2)  # Extended recovery time
                    
                    for _ in range(3):  # Try up to 3 times to get a new reference frame
                        recovery_frame = _capture_frame()
                        if recovery_frame is not None:
                            previous_frame = cv2.cvtColor(recovery_frame, cv2.COLOR_BGR2GRAY)
                            previous_frame = cv2.GaussianBlur(previous_frame, (21, 21), 0)
                            logger.info("Successfully recovered with new reference frame")
                            consecutive_failures = 0
                            break
                        time.sleep(1)
                
                continue
            
            # Reset failure counter on success
            consecutive_failures = 0
            
            # Process frame for motion detection
            gray_frame = cv2.cvtColor(current_frame_color, cv2.COLOR_BGR2GRAY)
            gray_frame = cv2.GaussianBlur(gray_frame, (21, 21), 0)
            
            # Compute absolute difference between current and previous frame
            frame_delta = cv2.absdiff(previous_frame, gray_frame)
            thresh = cv2.threshold(frame_delta, MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)[1]
            
            # Dilate the thresholded image to fill in holes
            thresh = cv2.dilate(thresh, None, iterations=2)
            
            # Find contours on thresholded image
            contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            # Check for motion - looking for contours of significant size
            motion_detected = False
            largest_area = 0
            
            for contour in contours:
                area = cv2.contourArea(contour)
                largest_area = max(largest_area, area)
                if area < MIN_MOTION_AREA:
                    continue
                motion_detected = True
                break
            
            # Update consecutive frame counter
            if motion_detected:
                consecutive_frames_with_motion += 1
                logger.debug(f"Motion detected in frame! Consecutive frames: {consecutive_frames_with_motion}")
            else:
                consecutive_frames_with_motion = 0
            
            # Periodic logging to show it's working
            frame_count += 1
            if frame_count % 10 == 0:  # Log every 10 frames
                logger.debug(f"Processing frame {frame_count}, motion={motion_detected}, "
                            f"consecutive={consecutive_frames_with_motion}, largest_area={largest_area}")
            
            # Check if we should trigger a motion event
            current_time = time.time()
            if (consecutive_frames_with_motion >= CONSECUTIVE_FRAMES_NEEDED and 
                current_time - last_motion_time > MOTION_COOLDOWN):
                
                logger.info(f"Motion detected! Consecutive frames: {consecutive_frames_with_motion}, "
                           f"largest contour: {largest_area}px")
                last_motion_time = current_time
                
                # Reset consecutive frames counter
                consecutive_frames_with_motion = 0
                
                # Save debug frame to help diagnose issues
                debug_folder = 'media/debug'
                if not os.path.exists(debug_folder):
                    os.makedirs(debug_folder)
                debug_file = f"{debug_folder}/motion_frame_{int(current_time)}.jpg"
                cv2.imwrite(debug_file, current_frame_color)
                logger.debug(f"Saved debug frame to {debug_file}")
                
                # If a callback was provided, call it
                if callback_on_motion:
                    try:
                        callback_on_motion()
                    except Exception as e:
                        logger.error(f"Error in motion callback: {e}")
            
            # Update previous frame
            previous_frame = gray_frame
        
        logger.info("Motion detection loop stopped cleanly")
        
    except Exception as e:
        logger.error(f"Error in motion detection: {e}")
        motion_active = False

def capture_motion_photo():
    """Capture a photo when motion is detected"""
    global camera_busy
    
    folder_path = 'media'
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{folder_path}/{timestamp}_motion.jpg"
    
    try:
        logger.info(f"Capturing motion photo: {filename}")
        
        # Mark camera as busy
        camera_busy = True
        
        # Take photo with libcamera-still
        subprocess.run([
            'libcamera-still',
            '-o', filename,
            '--nopreview',
            '--immediate',
            '--timeout', '1',
            # Higher quality settings for motion captures
            '--width', '1920',
            '--height', '1080'
        ], check=True, capture_output=True, timeout=5)  # Longer timeout for high-res captures
        
        logger.info(f"Motion photo saved: {filename}")
        
        # Add a short delay to let the camera reset
        time.sleep(1)
        
        # Mark camera as free
        camera_busy = False
        
        return filename
    except Exception as e:
        logger.error(f"Error capturing motion photo: {e}")
        camera_busy = False  # Reset busy flag
        return None

def start_motion_recording():
    """Start recording when motion is detected"""
    global camera_busy
    
    folder_path = 'media'
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_filename = f"{folder_path}/{timestamp}_motion_temp.h264"
    final_filename = f"{folder_path}/{timestamp}_motion.mp4"
    
    try:
        # Mark camera as busy
        camera_busy = True
        
        # Start recording
        logger.info(f"Starting motion recording: {temp_filename}")
        video_process = subprocess.Popen([
            'libcamera-vid',
            '-o', temp_filename,
            '--nopreview',
            '--width', '1280',
            '--height', '720',
            # Record for 10 seconds when motion is detected
            '-t', '10000'
        ])
        
        # Wait for recording to complete
        video_process.wait()
        
        # Convert to MP4
        logger.info(f"Converting motion recording to MP4: {final_filename}")
        result = subprocess.run([
            'ffmpeg',
            '-i', temp_filename,
            '-c:v', 'copy',
            final_filename,
            '-y'
        ], capture_output=True, text=True)
        
        # Mark camera as free
        camera_busy = False
        
        if result.returncode == 0:
            # Delete the temp file
            os.remove(temp_filename)
            logger.info(f"Motion video saved: {final_filename}")
            return final_filename
        else:
            # Fallback to h264
            final_h264 = temp_filename.replace('_motion_temp.h264', '_motion.h264')
            os.rename(temp_filename, final_h264)
            logger.info(f"Motion video saved as H264: {final_h264}")
            return final_h264
            
    except Exception as e:
        logger.error(f"Error in motion recording: {e}")
        camera_busy = False  # Reset busy flag
        return None

# Function to adjust motion detection settings
def update_motion_settings(threshold=None, min_area=None, cooldown=None, consecutive_frames=None):
    """Update motion detection settings"""
    global MOTION_THRESHOLD, MIN_MOTION_AREA, MOTION_COOLDOWN, CONSECUTIVE_FRAMES_NEEDED
    
    if threshold is not None:
        MOTION_THRESHOLD = int(threshold)
    if min_area is not None:
        MIN_MOTION_AREA = int(min_area)
    if cooldown is not None:
        MOTION_COOLDOWN = float(cooldown)
    if consecutive_frames is not None:
        CONSECUTIVE_FRAMES_NEEDED = int(consecutive_frames)
    
    logger.info(f"Motion settings updated: threshold={MOTION_THRESHOLD}, "
                f"min_area={MIN_MOTION_AREA}, cooldown={MOTION_COOLDOWN}, "
                f"consecutive_frames={CONSECUTIVE_FRAMES_NEEDED}")
    
    return {
        "threshold": MOTION_THRESHOLD,
        "min_area": MIN_MOTION_AREA,
        "cooldown": MOTION_COOLDOWN,
        "consecutive_frames": CONSECUTIVE_FRAMES_NEEDED
    }

# Helper function to get current motion settings
def get_motion_settings():
    """Return current motion detection settings"""
    return {
        "threshold": MOTION_THRESHOLD,
        "min_area": MIN_MOTION_AREA,
        "cooldown": MOTION_COOLDOWN,
        "consecutive_frames": CONSECUTIVE_FRAMES_NEEDED,
        "is_active": motion_active
    }

# Self-test function
def self_test():
    """Run a self-test of the motion detection system"""
    logger.info("Running motion detection self-test")
    
    try:
        # Test if we can capture a frame
        logger.info("Testing frame capture...")
        frame = _capture_frame()
        
        if frame is None:
            logger.error("Self-test failed: Could not capture frame")
            return False
        
        logger.info(f"Self-test: Frame captured successfully. Shape: {frame.shape}")
        
        # Test OpenCV operations
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (21, 21), 0)
        
        logger.info("Self-test: OpenCV operations successful")
        
        # Save a test image
        debug_folder = 'media/debug'
        if not os.path.exists(debug_folder):
            os.makedirs(debug_folder)
        test_file = f"{debug_folder}/self_test_{int(time.time())}.jpg"
        cv2.imwrite(test_file, frame)
        
        logger.info(f"Self-test: Saved test image to {test_file}")
        logger.info("Self-test completed successfully")
        
        return True
            
    except Exception as e:
        logger.error(f"Self-test failed: {e}")
        return False

# If running this file directly, run a self-test
if __name__ == "__main__":
    # Configure console logging when run directly
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter('%(levelname)s: %(message)s')
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    print("Running motion detection self-test...")
    if self_test():
        print("Self-test PASSED")
    else:
        print("Self-test FAILED")