import os
from dotenv import load_dotenv

# Carga variables de entorno desde .env
load_dotenv()

class Config:
    APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
    APP_PORT = int(os.getenv("APP_PORT", 5000))
    DEBUG = os.getenv("DEBUG", "True") == "True"