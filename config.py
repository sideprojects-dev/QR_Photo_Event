import os
from dotenv import load_dotenv

load_dotenv()  # load environment variables from .env file

CLIENT_SECRET_FILE = "client_secret.json"
FOLDER_ID = os.getenv("FOLDER_ID")
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
TOKEN_FILE = "token.json"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
