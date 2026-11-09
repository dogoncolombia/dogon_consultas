from supabase import create_client, Client
from flask import current_app


def get_supabase() -> Client:
    url = current_app.config["SUPABASE_URL"]
    key = current_app.config["SUPABASE_KEY"]
    if not url or not key:
        raise RuntimeError("Faltan SUPABASE_URL o SUPABASE_KEY en las variables de entorno.")
    return create_client(url, key)
