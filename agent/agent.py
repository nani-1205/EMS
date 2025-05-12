import time
import requests
import threading
import os
import datetime
import uuid
import logging
from PIL import ImageGrab # Use Pillow for screenshots
import psutil
# import pyautogui # Optional for idle detection

# Import configuration
try:
    import config
except ImportError:
    print("ERROR: config.py not found. Please create it with server details.")
    exit(1)


# --- Logging Setup ---
log_file = os.path.join(config.TEMP_DIR, 'monitor_agent.log')
logging.basicConfig(
    filename=log_file,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='a' # Append mode
)
# Also log to console for debugging when not running hidden
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler)


# --- Global State ---
last_activity_time = time.time()
current_activities = [] # Store activities between log intervals
activity_lock = threading.Lock()


# --- Helper Functions ---
def get_active_window_info():
    """Gets the title and process name of the currently active window."""
    try:
        # This part is OS-dependent and might need refinement
        # For Windows:
        if os.name == 'nt':
            import win32gui
            import win32process
            import win32api

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                window_title = win32gui.GetWindowText(hwnd)
                pid = win32process.GetWindowThreadProcessId(hwnd)[1]
                try:
                    process = psutil.Process(pid)
                    process_name = process.name()
                    # Optional: Get executable path
                    # exe_path = process.exe()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    process_name = "unknown_process"
                return window_title, process_name
            else:
                 return "No Active Window", "unknown_process" # Desktop or no focus
        # Add implementations for macOS/Linux if needed using different libraries
        else:
             # Basic psutil fallback (might not get foreground window reliably)
             # This needs a more specific cross-platform solution
             logging.warning("Active window detection not fully implemented for this OS.")
             return "Unknown Window", "unknown_process"

    except ImportError as e:
        logging.error(f"Required library not found for active window detection: {e}")
        return "Error Detecting Window", "error"
    except Exception as e:
        logging.error(f"Error getting active window: {e}", exc_info=True)
        return "Error Detecting Window", "error"

def take_screenshot():
    """Takes a screenshot and saves it to a temporary file."""
    try:
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        filename = f"screenshot_{timestamp.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(config.TEMP_DIR, filename)

        logging.info(f"Taking screenshot: {filename}")
        screenshot = ImageGrab.grab(all_screens=True) # Capture all monitors
        screenshot.save(filepath, "PNG")
        logging.info(f"Screenshot saved locally: {filepath}")
        return filepath, timestamp
    except Exception as e:
        logging.error(f"Failed to take screenshot: {e}", exc_info=True)
        return None, None

def send_data(endpoint, data=None, files=None):
    """Sends data to the server API."""
    url = f"{config.SERVER_URL}{endpoint}"
    headers = {'X-API-KEY': config.API_KEY}
    try:
        if files:
            response = requests.post(url, headers=headers, data=data, files=files, timeout=30)
        elif data:
             response = requests.post(url, headers=headers, json=data, timeout=15)
        else:
             response = requests.post(url, headers=headers, timeout=10) # For simple calls like heartbeat

        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        logging.info(f"Successfully sent data to {endpoint}. Status: {response.status_code}")
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to send data to {endpoint}: {e}")
        # Implement retry logic or local caching if needed
        return None
    except Exception as e:
         logging.error(f"Unexpected error sending data to {endpoint}: {e}", exc_info=True)
         return None


# --- Worker Threads ---
def screenshot_worker():
    """Periodically takes and uploads screenshots."""
    while True:
        try:
            filepath, timestamp = take_screenshot()
            if filepath and timestamp:
                files = {'screenshot': (os.path.basename(filepath), open(filepath, 'rb'), 'image/png')}
                payload = {
                    'employee_id': config.EMPLOYEE_ID,
                    'timestamp': timestamp.isoformat()
                }
                logging.info(f"Attempting to upload screenshot: {os.path.basename(filepath)}")
                response = send_data('/api/upload/screenshot', data=payload, files=files)

                # Close the file handle explicitly after request potentially finishes
                try:
                    files['screenshot'][1].close()
                except Exception as close_err:
                     logging.warning(f"Error closing screenshot file handle: {close_err}")


                if response and response.get("status") == "ok":
                    logging.info("Screenshot uploaded successfully.")
                    try:
                        os.remove(filepath) # Clean up temp file
                        logging.info(f"Removed temp screenshot: {filepath}")
                    except OSError as e:
                        logging.error(f"Failed to remove temp screenshot {filepath}: {e}")
                else:
                    logging.warning(f"Screenshot upload failed or server response was not ok. File kept: {filepath}")
                    # Implement logic to retry upload later if needed

        except Exception as e:
            logging.error(f"Error in screenshot_worker: {e}", exc_info=True)

        time.sleep(config.SCREENSHOT_INTERVAL_SECONDS)

def activity_monitor_worker():
    """Monitors active window and logs activity periods."""
    global current_activities
    last_window_title = None
    last_process_name = None
    activity_start_time = datetime.datetime.now(datetime.timezone.utc)

    while True:
        try:
            # --- Idle Detection (Optional - requires pyautogui or OS-specific methods) ---
            # current_time = time.time()
            # if current_time - last_activity_time > config.IDLE_THRESHOLD_SECONDS:
            #     is_active = False
            # else:
            #     is_active = True
            # Simple placeholder for now: assume always active when agent runs
            is_active = True
            # --- End Idle Detection ---

            window_title, process_name = get_active_window_info()

            # If the active window/process changes, log the previous activity period
            if (window_title != last_window_title or process_name != last_process_name) and last_window_title is not None:
                activity_end_time = datetime.datetime.now(datetime.timezone.utc)
                duration = (activity_end_time - activity_start_time).total_seconds()

                if duration > 1: # Only log significant activity periods (e.g., > 1 second)
                    activity_data = {
                        "window_title": last_window_title,
                        "process_name": last_process_name,
                        "start_time": activity_start_time.isoformat(),
                        "end_time": activity_end_time.isoformat(),
                        "duration_seconds": int(duration),
                        "is_active": is_active # Track if user was idle during this period
                    }
                    with activity_lock:
                        current_activities.append(activity_data)
                    logging.debug(f"Logged activity: {last_process_name} ({int(duration)}s)")

                # Start timing the new activity
                activity_start_time = activity_end_time

            # Update the last known state
            last_window_title = window_title
            last_process_name = process_name

            time.sleep(1) # Check active window every second (adjust as needed)

        except Exception as e:
            logging.error(f"Error in activity_monitor_worker: {e}", exc_info=True)
            time.sleep(5) # Wait a bit longer after an error

def activity_log_uploader_worker():
    """Periodically uploads the buffered activity logs."""
    global current_activities
    while True:
        time.sleep(config.ACTIVITY_LOG_INTERVAL_SECONDS)

        activities_to_send = []
        with activity_lock:
            if current_activities:
                activities_to_send = current_activities[:] # Make a copy
                current_activities = [] # Clear the buffer

        if activities_to_send:
            logging.info(f"Attempting to upload {len(activities_to_send)} activity logs.")
            payload = {
                'employee_id': config.EMPLOYEE_ID,
                'activities': activities_to_send
            }
            response = send_data('/api/log/activity', data=payload)
            if not response or response.get("status") != "ok":
                logging.warning("Failed to upload activity logs. Re-queueing is not implemented yet.")
                # NOTE: In a robust system, you'd re-add `activities_to_send`
                # back to `current_activities` or save them locally for retry.
        else:
             logging.info("No new activities to upload.")


def heartbeat_worker():
    """Sends periodic heartbeats to the server."""
    while True:
        try:
            logging.info("Sending heartbeat...")
            payload = {
                'employee_id': config.EMPLOYEE_ID,
                'hostname': config.EMPLOYEE_ID # Sending hostname again for clarity
                # Add other info like agent version, OS version?
            }
            send_data('/api/heartbeat', data=payload)
        except Exception as e:
            logging.error(f"Error in heartbeat_worker: {e}", exc_info=True)

        # Send heartbeat slightly less frequently than activity logs maybe
        time.sleep(config.ACTIVITY_LOG_INTERVAL_SECONDS * 2)

# --- Main Execution ---
if __name__ == "__main__":
    logging.info("Starting Monitoring Agent...")
    logging.info(f"Server URL: {config.SERVER_URL}")
    logging.info(f"Employee ID: {config.EMPLOYEE_ID}")
    logging.info(f"Temp Dir: {config.TEMP_DIR}")
    logging.info(f"Screenshot Interval: {config.SCREENSHOT_INTERVAL_SECONDS}s")
    logging.info(f"Activity Log Interval: {config.ACTIVITY_LOG_INTERVAL_SECONDS}s")

    # --- Create and Start Threads ---
    try:
        screenshot_thread = threading.Thread(target=screenshot_worker, daemon=True)
        activity_monitor_thread = threading.Thread(target=activity_monitor_worker, daemon=True)
        activity_uploader_thread = threading.Thread(target=activity_log_uploader_worker, daemon=True)
        heartbeat_thread = threading.Thread(target=heartbeat_worker, daemon=True)

        screenshot_thread.start()
        activity_monitor_thread.start()
        activity_uploader_thread.start()
        heartbeat_thread.start()

        logging.info("All worker threads started.")

        # Keep the main thread alive
        while True:
            # Optional: Add main thread logic if needed (e.g., check for commands from server)
            # Optional: Update last_activity_time based on mouse/keyboard input using pyautogui or OS hooks
            # Example placeholder:
            # last_activity_time = time.time() # Reset idle timer if activity detected
            time.sleep(60) # Keep main thread alive, check occasionally

    except KeyboardInterrupt:
        logging.info("Agent stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logging.error(f"Fatal error in main execution: {e}", exc_info=True)
    finally:
         logging.info("Monitoring Agent Shutting Down.")