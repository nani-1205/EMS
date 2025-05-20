# /root/EMS/agent/agent.py
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
    import config # Assuming config.py is in the same directory
except ImportError:
    # This log might not go to file if logging isn't set up yet,
    # but will print to console if agent is run directly.
    print("CRITICAL: config.py not found. Please ensure it exists in the agent directory.")
    logging.basicConfig(level=logging.CRITICAL) # Basic config for this critical error
    logging.critical("CRITICAL: config.py not found. Agent cannot start.")
    exit(1) # Exit if config is missing

# --- Logging Setup ---
# Ensure TEMP_DIR exists or handle its creation failure gracefully
if not os.path.exists(config.TEMP_DIR):
    try:
        os.makedirs(config.TEMP_DIR, exist_ok=True)
    except OSError as e:
        # Fallback logging if TEMP_DIR cannot be created
        print(f"CRITICAL: Could not create TEMP_DIR {config.TEMP_DIR}: {e}. Logging to current directory.")
        config.TEMP_DIR = "." # Log to current directory as a last resort

log_file = os.path.join(config.TEMP_DIR, 'monitor_agent.log')
logging.basicConfig(
    filename=log_file,
    level=logging.DEBUG, # Set to DEBUG for detailed troubleshooting
    format='%(asctime)s - %(levelname)s - %(threadName)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s',
    filemode='a' # Append mode
)
# Console Handler for visible output when not running hidden
console_handler = logging.StreamHandler()
# You might want INFO for console to be less verbose than file log during dev
console_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logging.getLogger().addHandler(console_handler) # Add console handler to root logger


# --- Global State ---
last_user_activity_time = time.time() # For idle detection (if you implement it)
current_activities = [] # Store activities between log intervals
activity_lock = threading.Lock() # Lock for accessing current_activities


# --- Helper Functions ---
def get_active_window_info():
    """Gets the title and process name of the currently active window."""
    window_title = "Unknown Window" # Default
    process_name = "unknown_process" # Default
    try:
        if os.name == 'nt':
            import win32gui
            import win32process
            # import win32api # Not used in this function

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                window_title_raw = win32gui.GetWindowText(hwnd)
                window_title = window_title_raw if window_title_raw else "No Title Window"

                # Getting process ID
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                except Exception as e_pid:
                    logging.error(f"Error getting PID for HWND {hwnd}: {e_pid}")
                    pid = 0 # Fallback

                if pid == 0: # Idle process or system process without a clear owner
                    process_name = "System Idle/Background"
                else:
                    try:
                        process = psutil.Process(pid)
                        process_name = process.name()
                        # exe_path = process.exe() # Optional: get full path
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e_psu_proc:
                        process_name = f"Protected/Zombie Process (PID: {pid})"
                        logging.warning(f"Psutil: Could not get process name for PID {pid}: {e_psu_proc}")
                    except Exception as e_psutil_other:
                        process_name = f"Error Psutil (PID: {pid})"
                        logging.error(f"Psutil: Other error for PID {pid}: {e_psutil_other}", exc_info=False)
            else:
                window_title = "No Active Window" # E.g., Desktop is active
                process_name = "System Desktop/Background"
        else: # Placeholder for other OS
            logging.warning("Active window detection not fully implemented for non-Windows OS.")
            window_title = "Unsupported OS Window"
            process_name = "Unsupported OS Process"

    except ImportError as e_imp:
        logging.error(f"ImportError for active window detection (win32gui/psutil likely missing): {e_imp}")
        window_title = "Error Importing Libs"
    except Exception as e_gen:
        # Log the full traceback for unexpected errors
        logging.error(f"General error in get_active_window_info: {e_gen}", exc_info=True)
        window_title = "Error Detecting Window"

    logging.debug(f"Detected active window: Title='{window_title}', Process='{process_name}'")
    return window_title, process_name

def take_screenshot():
    """Takes a screenshot and saves it to a temporary file."""
    try:
        timestamp = datetime.datetime.now(datetime.timezone.utc)
        # Create a more unique filename to avoid rare collisions if multiple agents share TEMP_DIR (not typical)
        filename = f"screenshot_{timestamp.strftime('%Y%m%d_%H%M%S%f')}_{config.EMPLOYEE_ID}_{uuid.uuid4().hex[:6]}.png"
        filepath = os.path.join(config.TEMP_DIR, filename)

        logging.info(f"Attempting to take screenshot: {filename}")
        screenshot = ImageGrab.grab(all_screens=True) # Capture all monitors
        screenshot.save(filepath, "PNG")
        logging.info(f"Screenshot saved locally: {filepath}")
        return filepath, timestamp
    except Exception as e:
        logging.error(f"Failed to take screenshot: {e}", exc_info=True)
        return None, None

def send_data(endpoint, data=None, files=None):
    """Sends data to the server API with retries."""
    url = f"{config.SERVER_URL}{endpoint}"
    headers = {'X-API-KEY': config.API_KEY, 'User-Agent': f'MonitoringAgent/{config.EMPLOYEE_ID}'} # Added User-Agent
    max_retries = config.MAX_UPLOAD_RETRIES if hasattr(config, 'MAX_UPLOAD_RETRIES') else 3
    retry_delay = config.UPLOAD_RETRY_DELAY if hasattr(config, 'UPLOAD_RETRY_DELAY') else 10 # seconds

    for attempt in range(max_retries):
        try:
            if files:
                logging.debug(f"Attempt {attempt+1}: Sending POST (files) to {url}. Form data keys: {list(data.keys()) if data else 'None'}. File part name: {list(files.keys())[0] if files else 'None'}")
                response = requests.post(url, headers=headers, data=data, files=files, timeout=60) # Increased timeout for uploads
            elif data:
                 # Log only a snippet of potentially large data for privacy/log size
                data_preview = {k: (str(v)[:100] + '...' if len(str(v)) > 100 else v) for k, v in data.items() if k != 'activities'}
                if 'activities' in data: data_preview['activities_count'] = len(data['activities'])

                logging.debug(f"Attempt {attempt+1}: Sending POST (json) to {url}. Payload sample: {data_preview}")
                response = requests.post(url, headers=headers, json=data, timeout=30) # Timeout for JSON data
            else: # For simple calls like heartbeat
                 logging.debug(f"Attempt {attempt+1}: Sending POST (no body) to {url}.")
                 response = requests.post(url, headers=headers, timeout=15)

            # Log basic response info
            logging.info(f"Response from {url} (Attempt {attempt+1}): Status {response.status_code}, Response text (first 200 chars): {response.text[:200]}")
            response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
            logging.info(f"Successfully sent data to {endpoint} on attempt {attempt+1}.")
            try:
                return response.json() # Attempt to parse JSON from successful response
            except requests.exceptions.JSONDecodeError as json_err:
                logging.error(f"Could not decode JSON response from {endpoint} even with 2xx status: {json_err}. Response text: {response.text[:500]}")
                return {"status": "ok_no_json", "message": "Server responded successfully but not with JSON."} # Or return None

        except requests.exceptions.Timeout:
            logging.warning(f"Attempt {attempt + 1}/{max_retries} - Timeout connecting to {endpoint}.")
        except requests.exceptions.ConnectionError:
            logging.warning(f"Attempt {attempt + 1}/{max_retries} - Connection error to {endpoint}. Server might be down or unreachable.")
        except requests.exceptions.HTTPError as http_err: # 4xx or 5xx errors
            logging.error(f"Attempt {attempt + 1}/{max_retries} - HTTP error for {endpoint}: {http_err}. Status: {http_err.response.status_code}. Response: {http_err.response.text[:500]}")
            # For 401 Unauthorized, retrying might not help if API key is wrong.
            if http_err.response.status_code == 401:
                logging.critical("CRITICAL: Received 401 Unauthorized. Check API_KEY. Stopping retries for this call.")
                return None # Don't retry on 401
            # For other client errors (4xx), retrying might also not help.
            # For server errors (5xx), retrying is often useful.
        except Exception as e_gen:
            logging.error(f"Attempt {attempt + 1}/{max_retries} - Unexpected error sending data to {endpoint}: {e_gen}", exc_info=True)
        
        if attempt + 1 < max_retries:
            logging.info(f"Retrying {endpoint} in {retry_delay} seconds...")
            time.sleep(retry_delay)
        else:
            logging.error(f"Max retries ({max_retries}) reached for {endpoint}. Giving up on this request.")
    return None # Return None if all retries fail


# --- Worker Threads ---
def screenshot_worker():
    logging.info("Screenshot worker thread started.")
    while True:
        try:
            filepath, timestamp = take_screenshot()
            if filepath and timestamp:
                with open(filepath, 'rb') as f_screenshot:
                    files_payload = {'screenshot': (os.path.basename(filepath), f_screenshot, 'image/png')}
                    form_payload = {
                        'employee_id': config.EMPLOYEE_ID,
                        'timestamp': timestamp.isoformat()
                    }
                    logging.info(f"Attempting to upload screenshot: {os.path.basename(filepath)}")
                    response_json = send_data('/api/upload/screenshot', data=form_payload, files=files_payload)
                
                # File is closed automatically when 'with open' block exits

                if response_json and response_json.get("status") == "ok":
                    logging.info("Screenshot uploaded successfully.")
                    try:
                        os.remove(filepath)
                        logging.info(f"Removed temp screenshot: {filepath}")
                    except OSError as e_os:
                        logging.error(f"Failed to remove temp screenshot {filepath}: {e_os}")
                else:
                    logging.warning(f"Screenshot upload failed or server response not 'ok'. Response: {response_json}. File kept: {filepath}")
            else:
                logging.warning("Screenshot taking failed, skipping upload for this cycle.")
        except Exception as e:
            logging.error(f"Unhandled error in screenshot_worker loop: {e}", exc_info=True)
        
        logging.debug(f"Screenshot worker sleeping for {config.SCREENSHOT_INTERVAL_SECONDS} seconds.")
        time.sleep(config.SCREENSHOT_INTERVAL_SECONDS)


def activity_monitor_worker():
    global current_activities, last_user_activity_time # last_user_activity_time not used yet
    last_window_title = None
    last_process_name = None
    activity_start_time = None 
    logging.info("Activity monitor worker thread started.")

    while True:
        try:
            is_active = True # Placeholder: Implement proper idle detection later

            current_title, current_process = get_active_window_info()
            now_utc = datetime.datetime.now(datetime.timezone.utc)

            if activity_start_time is None: # Initialize on first run or after logging
                activity_start_time = now_utc
                last_window_title = current_title
                last_process_name = current_process
                logging.debug(f"Initial activity tracking: Title='{last_window_title[:50]}', Process='{last_process_name}' at {activity_start_time.isoformat()}")

            # Log if window/process changes OR if current activity is too long (optional)
            significant_change = (current_title != last_window_title or current_process != last_process_name)
            
            if significant_change and last_window_title is not None: # Check last_window_title to ensure there's a previous state
                duration_seconds = (now_utc - activity_start_time).total_seconds()
                logging.debug(f"Activity change detected. Prev: T='{last_window_title[:50]}', P='{last_process_name}'. New: T='{current_title[:50]}', P='{current_process}'. Duration: {duration_seconds:.2f}s")

                if duration_seconds >= 1.0: # Log activities lasting at least 1 second
                    activity_data = {
                        "window_title": last_window_title if last_window_title else "N/A",
                        "process_name": last_process_name if last_process_name else "N/A",
                        "start_time": activity_start_time.isoformat(),
                        "end_time": now_utc.isoformat(),
                        "duration_seconds": int(round(duration_seconds)),
                        "is_active": is_active 
                    }
                    with activity_lock:
                        current_activities.append(activity_data)
                    logging.info(f"Logged activity: P='{activity_data['process_name']}', T='{activity_data['window_title'][:30]}', Dur={activity_data['duration_seconds']}s")
                else:
                    logging.debug(f"Skipping very short activity ({duration_seconds:.2f}s) for P='{last_process_name}'")
                
                # Reset for the new/current activity
                activity_start_time = now_utc
                last_window_title = current_title
                last_process_name = current_process
            elif activity_start_time is not None and (now_utc - activity_start_time).total_seconds() > (config.ACTIVITY_LOG_INTERVAL_SECONDS * 10) and last_window_title:
                # Optional: Force log a long-running activity to prevent huge single entries
                # This logic might need refinement based on desired behavior.
                duration_seconds = (now_utc - activity_start_time).total_seconds()
                logging.info(f"Logging long-running activity due to timeout. P='{last_process_name}', T='{last_window_title[:30]}', Dur={int(round(duration_seconds))}s")
                activity_data = {
                    "window_title": last_window_title, "process_name": last_process_name,
                    "start_time": activity_start_time.isoformat(), "end_time": now_utc.isoformat(),
                    "duration_seconds": int(round(duration_seconds)), "is_active": is_active
                }
                with activity_lock: current_activities.append(activity_data)
                activity_start_time = now_utc # Reset start time for this continuing activity


            time.sleep(1) # Check active window every second (adjust as needed for performance/granularity)

        except Exception as e:
            logging.error(f"Error in activity_monitor_worker: {e}", exc_info=True)
            activity_start_time = None # Reset state on error
            time.sleep(5) # Wait a bit longer after an error


def activity_log_uploader_worker():
    global current_activities
    logging.info("Activity log uploader worker thread started.")
    while True:
        upload_interval = config.ACTIVITY_LOG_INTERVAL_SECONDS
        logging.debug(f"Activity uploader sleeping for {upload_interval} seconds.")
        time.sleep(upload_interval)

        activities_to_send = []
        with activity_lock:
            if current_activities:
                activities_to_send = list(current_activities) # Shallow copy
                current_activities.clear() 
        
        if activities_to_send:
            logging.info(f"Preparing to upload {len(activities_to_send)} activity log(s).")
            payload = {
                'employee_id': config.EMPLOYEE_ID,
                'activities': activities_to_send # This is a list of dicts
            }
            # For extremely verbose debugging of the exact payload:
            # import json
            # logging.debug(f"Full payload for /api/log/activity: {json.dumps(payload, indent=2)}")
            response_json = send_data('/api/log/activity', data=payload)
            
            if response_json and response_json.get("status") == "ok":
                logging.info(f"Successfully uploaded {len(activities_to_send)} activity logs. Server msg: {response_json.get('message')}")
            else:
                logging.warning(f"Failed to upload activity logs or server error. {len(activities_to_send)} logs were attempted. Server response: {response_json}. Data not re-queued.")
                # Robust implementation: Save activities_to_send to a local file for retry.
        else:
             logging.debug("No new activities to upload in this cycle.")


def heartbeat_worker():
    logging.info("Heartbeat worker thread started.")
    while True:
        heartbeat_interval = max(60, config.ACTIVITY_LOG_INTERVAL_SECONDS * 2) # Ensure at least 60s
        try:
            logging.info("Sending heartbeat...")
            payload = {
                'employee_id': config.EMPLOYEE_ID,
                'hostname': socket.gethostname() if 'socket' in globals() else config.EMPLOYEE_ID # Send current hostname
            }
            send_data('/api/heartbeat', data=payload)
        except Exception as e:
            logging.error(f"Error in heartbeat_worker: {e}", exc_info=True)
        
        logging.debug(f"Heartbeat worker sleeping for {heartbeat_interval} seconds.")
        time.sleep(heartbeat_interval)

# --- Main Execution ---
if __name__ == "__main__":
    # Import socket here for hostname if not already imported (e.g. in config)
    try:
        import socket
    except ImportError:
        logging.warning("Socket module not found, hostname in heartbeat might be affected if not set in config.")


    logging.info(f"--- Starting Monitoring Agent v1.1 ---") # Example version
    logging.info(f"Server URL: {config.SERVER_URL}")
    logging.info(f"Employee ID (from config): {config.EMPLOYEE_ID}")
    logging.info(f"Actual Hostname: {socket.gethostname() if 'socket' in globals() else 'N/A'}")
    logging.info(f"Temp Dir: {config.TEMP_DIR}")
    logging.info(f"Screenshot Interval: {config.SCREENSHOT_INTERVAL_SECONDS}s")
    logging.info(f"Activity Log Upload Interval: {config.ACTIVITY_LOG_INTERVAL_SECONDS}s")
    logging.info(f"Python version: {os.sys.version}")
    logging.info(f"Psutil version: {psutil.__version__ if hasattr(psutil, '__version__') else 'Unknown'}")
    logging.info(f"Pillow version: {ImageGrab.PILLOW_VERSION if hasattr(ImageGrab, 'PILLOW_VERSION') else 'Unknown'}")


    try:
        screenshot_thread = threading.Thread(target=screenshot_worker, name="ScreenshotThread", daemon=True)
        activity_monitor_thread = threading.Thread(target=activity_monitor_worker, name="ActivityMonitorThread", daemon=True)
        activity_uploader_thread = threading.Thread(target=activity_log_uploader_worker, name="ActivityUploaderThread", daemon=True)
        heartbeat_thread = threading.Thread(target=heartbeat_worker, name="HeartbeatThread", daemon=True)

        threads = [screenshot_thread, activity_monitor_thread, activity_uploader_thread, heartbeat_thread]
        for t in threads:
            t.start()

        logging.info("All worker threads started.")

        # Keep the main thread alive, can also be used for graceful shutdown logic
        while True:
            all_threads_alive = all(t.is_alive() for t in threads)
            if not all_threads_alive:
                logging.error("One or more worker threads have died. Agent might not be functioning correctly.")
                # Attempt to restart threads or exit, depending on desired robustness
                break # Exit main loop if a thread dies for this example
            time.sleep(60) # Check thread status periodically

    except KeyboardInterrupt:
        logging.info("Agent shutdown initiated by user (KeyboardInterrupt).")
    except Exception as e:
        logging.critical(f"Fatal unhandled error in main agent execution: {e}", exc_info=True)
    finally:
         logging.info("--- Monitoring Agent Shutting Down ---")