import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    APP_NAME = os.getenv("APP_NAME", "Dogon")
    QUERY_COST = float(os.getenv("QUERY_COST", "400"))
    RECHARGE_MIN_AMOUNT = float(os.getenv("RECHARGE_MIN_AMOUNT", "5000"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() in {"true", "1", "yes"}
