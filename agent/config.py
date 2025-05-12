import os
from dotenv import load_dotenv

# Load environment variables if .env exists in agent dir (less common)
# basedir = os.path.abspath(os.path.dirname(__file__))
# load_dotenv(os.path.join(basedir, '.env'))

# Configuration - *** IMPORTANT: Embedding secrets is risky! ***
# Consider fetching config from server after initial registration/auth,
# or using an installer that sets these.
SERVER_URL = "http://your_server_ip_or_domain:5000" # CHANGE THIS
API_KEY = "super_secret_agent_api_key"            # CHANGE THIS (Must match server .env)

# Use a unique ID for the employee. Could be machine ID, username, etc.
# Using hostname as a simple default, but ideally should be configurable/assigned.
try:
    import socket
    EMPLOYEE_ID = socket.gethostname()
except ImportError:
    EMPLOYEE_ID = "unknown_employee"


# Agent Settings
SCREENSHOT_INTERVAL_SECONDS = 60 * 5  # Every 5 minutes
ACTIVITY_LOG_INTERVAL_SECONDS = 60 * 1 # Every 1 minute
IDLE_THRESHOLD_SECONDS = 60 * 3 # 3 minutes of no activity = idle

# --- Internal Use ---
# Get temporary directory for storing screenshots before upload
TEMP_DIR = os.path.join(os.environ.get('TEMP', '/tmp'), 'monitor_agent_cache')
if not os.path.exists(TEMP_DIR):
    try:
        os.makedirs(TEMP_DIR)
    except OSError as e:
        print(f"Error creating temp directory {TEMP_DIR}: {e}")
        # Fallback or handle error appropriately
        TEMP_DIR = '.' # Use current directory as fallback