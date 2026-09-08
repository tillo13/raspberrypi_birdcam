#!/usr/bin/env python3
"""
Sense HAT utility functions for Bird Cam
Basic LED feedback for camera operations only
Updated with snake animation for recording and radar animation for live mode
"""

from sense_hat import SenseHat
import time
import logging
import threading
import random
import math

# Set up logging
logger = logging.getLogger('sensehat_utils')
logger.setLevel(logging.INFO)

# Fixed rotation for USB ports at top
ROTATION = 180

try:
    # Initialize Sense HAT
    sense = SenseHat()
    sense.set_rotation(ROTATION)
    logger.info(f"Sense HAT initialized successfully with {ROTATION}° rotation")
except Exception as e:
    logger.error(f"Failed to initialize Sense HAT: {e}")
    raise

# Define colors
RED = [255, 0, 0]
ORANGE = [255, 165, 0]
YELLOW = [255, 255, 0]
WHITE = [255, 255, 255]
GREEN = [0, 255, 0]
BLACK = [0, 0, 0]
BLUE = [0, 0, 255]
CYAN = [0, 255, 255]

# Thread control for animations
recording_active = False
recording_thread = None
live_mode_active = False
live_mode_thread = None

def ensure_rotation():
    """Ensure rotation is set correctly"""
    sense.set_rotation(ROTATION)

def clear_display():
    """Clear the LED matrix"""
    ensure_rotation()
    sense.clear()

def show_startup_message():
    """Display startup message"""
    ensure_rotation()
    sense.show_message("Web!", text_colour=(0, 255, 0), scroll_speed=0.05)
    clear_display()

def create_ring_pattern(ring_size, color):
    """Create a ring pattern on the 8x8 LED matrix"""
    pattern = [[BLACK for _ in range(8)] for _ in range(8)]
    
    if ring_size == 4:  # Outer ring
        for i in range(8):
            pattern[0][i] = color
            pattern[7][i] = color
        for i in range(1, 7):
            pattern[i][0] = color
            pattern[i][7] = color
    
    elif ring_size == 3:  # Second ring
        for i in range(1, 7):
            pattern[1][i] = color
            pattern[6][i] = color
        for i in range(2, 6):
            pattern[i][1] = color
            pattern[i][6] = color
    
    elif ring_size == 2:  # Third ring
        for i in range(2, 6):
            pattern[2][i] = color
            pattern[5][i] = color
        for i in range(3, 5):
            pattern[i][2] = color
            pattern[i][5] = color
    
    elif ring_size == 1:  # Center
        for i in range(3, 5):
            for j in range(3, 5):
                pattern[i][j] = color
    
    # Flatten the pattern for sense HAT
    flat_pattern = []
    for row in pattern:
        flat_pattern.extend(row)
    
    return flat_pattern

def photo_countdown():
    """Display countdown rings before taking photo"""
    ensure_rotation()
    
    # Ring 4 - Red (outer)
    sense.set_pixels(create_ring_pattern(4, RED))
    time.sleep(0.5)
    
    # Ring 3 - Orange (add to existing)
    pattern = create_ring_pattern(4, RED)
    orange_ring = create_ring_pattern(3, ORANGE)
    for i in range(len(pattern)):
        if orange_ring[i] != BLACK:
            pattern[i] = orange_ring[i]
    sense.set_pixels(pattern)
    time.sleep(0.5)
    
    # Ring 2 - Yellow (add to existing)
    yellow_ring = create_ring_pattern(2, YELLOW)
    for i in range(len(pattern)):
        if yellow_ring[i] != BLACK:
            pattern[i] = yellow_ring[i]
    sense.set_pixels(pattern)
    time.sleep(0.5)
    
    # Ring 1 - White center (full display)
    white_center = create_ring_pattern(1, WHITE)
    for i in range(len(pattern)):
        if white_center[i] != BLACK:
            pattern[i] = white_center[i]
    sense.set_pixels(pattern)
    time.sleep(0.3)
    
    # Flash white
    sense.clear(255, 255, 255)

def show_photo_success():
    """Show success animation after photo"""
    ensure_rotation()
    sense.clear(0, 255, 0)
    time.sleep(0.1)
    sense.clear()

def show_photo_error():
    """Show error animation for photo failure"""
    ensure_rotation()
    sense.clear(255, 0, 0)
    time.sleep(0.2)
    sense.clear()

def recording_snake_animation():
    """Thread function that runs the snake animation while recording"""
    global recording_active
    
    # Initialize snake
    snake = [(0, 0), (0, 1), (0, 2)]
    direction = (0, 1)  # Moving down
    speed = 0.2  # seconds between moves
    last_move_time = time.time()
    
    # Colors for the snake (head to tail gradient)
    snake_colors = [
        [255, 0, 0],    # Red (head)
        [255, 100, 0],  # Orange-ish
        [255, 200, 0],  # Yellow-ish
    ]
    
    # Recording indicator animation loop
    while recording_active:
        current_time = time.time()
        
        # Move the snake at regular intervals
        if current_time - last_move_time >= speed:
            # Clear the display
            sense.clear()
            
            # Get current head position
            head_x, head_y = snake[0]
            
            # Determine new head position based on direction
            new_head_x = (head_x + direction[0]) % 8
            new_head_y = (head_y + direction[1]) % 8
            new_head = (new_head_x, new_head_y)
            
            # Add new head and remove tail
            snake.insert(0, new_head)
            snake.pop()
            
            # Randomly change direction occasionally (15% chance)
            if random.random() < 0.15:
                # Possible directions: up, right, down, left
                directions = [(0, -1), (1, 0), (0, 1), (-1, 0)]
                # Don't go backwards (opposite of current direction)
                opposite = (-direction[0], -direction[1])
                directions.remove(opposite)
                direction = random.choice(directions)
            
            # Draw the snake
            for i, (x, y) in enumerate(snake):
                if i < len(snake_colors):
                    sense.set_pixel(x, y, *snake_colors[i])
                else:
                    # Use the last color for any remaining segments
                    sense.set_pixel(x, y, *snake_colors[-1])
            
            # Add a blinking red "REC" indicator in the corner
            if int(current_time) % 2 == 0:  # Blink every second
                # Draw a small "REC" indicator in the corner (just a red dot)
                sense.set_pixel(7, 7, 255, 0, 0)
            
            last_move_time = current_time
        
        # Short sleep to prevent CPU hogging
        time.sleep(0.05)

def show_recording_active():
    """Show recording indicator with moving snake animation"""
    global recording_active, recording_thread
    
    ensure_rotation()
    
    # Start the recording animation in a separate thread
    recording_active = True
    if recording_thread is None or not recording_thread.is_alive():
        recording_thread = threading.Thread(target=recording_snake_animation, daemon=True)
        recording_thread.start()
        logger.info("Started recording snake animation")

def stop_recording_animation():
    """Stop the recording animation thread"""
    global recording_active
    recording_active = False
    # Give the thread a moment to finish
    time.sleep(0.3)
    # Clear the display
    clear_display()

def show_recording_converting():
    """Show converting video indicator"""
    ensure_rotation()
    # First stop any ongoing recording animation
    stop_recording_animation()
    # Then show the converting indicator
    sense.clear(255, 255, 0)

def show_recording_success():
    """Show success animation after recording"""
    ensure_rotation()
    # Make sure recording animation is stopped
    stop_recording_animation()
    # Show success flash
    sense.clear(0, 255, 0)
    time.sleep(0.2)
    sense.clear()

def show_recording_warning():
    """Show warning for recording (fallback to h264)"""
    ensure_rotation()
    # Make sure recording animation is stopped
    stop_recording_animation()
    # Show warning flash
    sense.clear(255, 100, 0)
    time.sleep(0.2)
    sense.clear()

def show_recording_error():
    """Show error for recording failure"""
    ensure_rotation()
    # Make sure recording animation is stopped
    stop_recording_animation()
    # Show error
    sense.clear(255, 0, 0)
    time.sleep(0.5)
    clear_display()

def live_mode_animation():
    """Thread function that runs a radar/pulse animation for live mode"""
    global live_mode_active
    
    # Center of the radar
    center_x, center_y = 3.5, 3.5
    
    # Animation parameters
    max_radius = 5.0  # Maximum radius of the radar sweep
    angle = 0  # Starting angle
    rotation_speed = 6  # Degrees per frame
    frames_per_second = 15
    
    # Live mode animation loop
    while live_mode_active:
        # Clear the display
        sense.clear()
        
        # Update the angle for rotation
        angle = (angle + rotation_speed) % 360
        angle_rad = math.radians(angle)
        
        # Draw radar sweep line
        for r in range(1, int(max_radius) + 1):
            x = center_x + r * math.cos(angle_rad)
            y = center_y + r * math.sin(angle_rad)
            
            # Convert to integers and check if in bounds
            ix, iy = int(round(x)), int(round(y))
            if 0 <= ix < 8 and 0 <= iy < 8:
                # Brighter at the tip, dimmer at the base
                intensity = int(255 * (r / max_radius))
                sense.set_pixel(ix, iy, 0, intensity, intensity)  # Cyan-ish color
        
        # Draw a small pulse effect at the center
        pulse_size = 1 + 0.5 * math.sin(time.time() * 4)  # Pulsing effect
        for x in range(8):
            for y in range(8):
                # Calculate distance from center
                dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                if dist < pulse_size:
                    # Create gradient from center (bright) to edge (dim)
                    intensity = int(200 * (1 - dist/pulse_size))
                    # Blend with existing pixel (for sweep line)
                    current = sense.get_pixel(x, y)
                    if current == [0, 0, 0]:  # If pixel is black
                        sense.set_pixel(x, y, 0, intensity, 255)  # Blue-cyan for pulse
        
        # Add "LIVE" indicator in corner
        if int(time.time() * 2) % 2 == 0:  # Blink twice per second
            sense.set_pixel(0, 0, 0, 200, 255)  # Cyan indicator
        
        # Frame timing
        time.sleep(1.0 / frames_per_second)

def start_live_mode():
    """Start the live mode animation"""
    global live_mode_active, live_mode_thread
    
    ensure_rotation()
    
    # Start the live mode animation in a separate thread
    live_mode_active = True
    if live_mode_thread is None or not live_mode_thread.is_alive():
        live_mode_thread = threading.Thread(target=live_mode_animation, daemon=True)
        live_mode_thread.start()
        logger.info("Started live mode animation")

def stop_live_mode():
    """Stop the live mode animation"""
    global live_mode_active
    live_mode_active = False
    # Give the thread a moment to finish
    time.sleep(0.3)
    # Clear the display
    clear_display()

def always_on_display():
    """Show a simple status indicator instead of temperature"""
    ensure_rotation()
    
    # Only show if we're not recording or in live mode (to avoid conflicts)
    global recording_active, live_mode_active
    if recording_active or live_mode_active:
        return
    
    # Rotating colors for the status pixel
    colors = [
        (50, 0, 0),    # Dim red
        (0, 50, 0),    # Dim green  
        (0, 0, 50),    # Dim blue
        (50, 50, 0),   # Dim yellow
        (50, 0, 50),   # Dim magenta
        (0, 50, 50),   # Dim cyan
    ]
    
    # Use current time to select color (changes each call)
    import time as time_module
    color_index = int(time_module.time()) % len(colors)
    color = colors[color_index]
    
    # Single dim pixel in corner to show it's active
    sense.set_pixel(0, 0, color[0], color[1], color[2])
    time.sleep(0.1)
    sense.set_pixel(0, 0, 0, 0, 0)   # Turn it off

def show_random_display():
    """Placeholder function - does nothing"""
    # This function is called by app.py but we don't want random displays
    pass