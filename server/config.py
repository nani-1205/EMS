import os
from dotenv import load_dotenv
from urllib.parse import quote_plus # <--- IMPORTED

# Load environment variables from .env file
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    FLASK_ENV = os.environ.get('FLASK_ENV') or 'production'

    # MongoDB Config
    MONGO_HOSTNAME = os.environ.get('MONGO_HOSTNAME')
    MONGO_PORT = int(os.environ.get('MONGO_PORT') or 27017)
    MONGO_USERNAME = os.environ.get('MONGO_USERNAME')
    MONGO_PASSWORD = os.environ.get('MONGO_PASSWORD')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME')
    MONGO_AUTH_DB = os.environ.get('MONGO_AUTH_DB') or 'admin'

    # --- UPDATED SECTION ---
    if MONGO_USERNAME and MONGO_PASSWORD:
        # URL-encode username and password for safe inclusion in the URI
        encoded_username = quote_plus(MONGO_USERNAME)
        encoded_password = quote_plus(MONGO_PASSWORD)
        MONGO_URI = f"mongodb://{encoded_username}:{encoded_password}@{MONGO_HOSTNAME}:{MONGO_PORT}/{MONGO_DB_NAME}?authSource={MONGO_AUTH_DB}"
    else:
        # Connection string without authentication
         MONGO_URI = f"mongodb://{MONGO_HOSTNAME}:{MONGO_PORT}/{MONGO_DB_NAME}"
    # --- END UPDATED SECTION ---

    # Agent Config
    AGENT_API_KEY = os.environ.get('AGENT_API_KEY')

    # Uploads folder
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads', 'screenshots')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # Example: 16MB limit for uploads

    # Create upload folder if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        try:
            os.makedirs(UPLOAD_FOLDER)
        except OSError as e:
            print(f"Warning: Could not create upload folder {UPLOAD_FOLDER}: {e}")
            # Consider how to handle this if uploads are critical

    # Temp storage for agent executable (replace with actual path after building)
    AGENT_EXE_PATH = os.path.join(basedir, '..', 'EXE', 'TekPossibleMonitorAgent_Setup_1.0.exe') # Adjust path as needed