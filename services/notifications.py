def send_negative_report_notification(phone: str, message: str) -> dict:
    return {
        "enabled": False,
        "message": "Integración Twilio pendiente. Notificación simulada.",
        "phone": phone,
        "content": message,
    }
