def create_wompi_checkout(user_id: str, amount: float) -> dict:
    return {
        "enabled": False,
        "message": "Integración Wompi pendiente. Usa la recarga demo mientras conectamos la pasarela.",
        "user_id": user_id,
        "amount": amount,
    }


def process_wompi_webhook(payload: dict) -> dict:
    return {
        "ok": True,
        "message": "Webhook recibido en modo stub. Integra la validación de firma y actualización de saldo después.",
        "payload": payload,
    }
