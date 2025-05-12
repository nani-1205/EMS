import os
from dotenv import load_dotenv

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

    if MONGO_USERNAME and MONGO_PASSWORD:
        MONGO_URI = f"mongodb://{MONGO_USERNAME}:{MONGO_PASSWORD}@{MONGO_HOSTNAME}:{MONGO_PORT}/{MONGO_DB_NAME}?authSource={MONGO_AUTH_DB}"
    else:
         MONGO_URI = f"mongodb://{MONGO_HOSTNAME}:{MONGO_PORT}/{MONGO_DB_NAME}"

    # Agent Config
    AGENT_API_KEY = os.environ.get('AGENT_API_KEY')

    # Uploads folder
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads', 'screenshots')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024 # Example: 16MB limit for uploads

    # Create upload folder if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    # Temp storage for agent executable (replace with actual path after building)
    AGENT_EXE_PATH = os.path.join(basedir, '..', 'agent', 'dist', 'monitoring_agent.exe') # Adjust path as needed