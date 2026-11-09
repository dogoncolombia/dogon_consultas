"""Shared traffic-light thresholds for active report counts."""


def report_status(count: int) -> dict:
    if count >= 3:
        return {"class": "risk-high", "label": "Rojo · 3 o más reportes", "color": "rojo"}
    if count >= 1:
        return {"class": "risk-medium", "label": "Amarillo · 1–2 reportes", "color": "amarillo"}
    return {"class": "risk-low", "label": "Verde · Sin reportes", "color": "verde"}


def fetch_report_pages(query) -> list:
    """Read all matches, with deterministic order across API pages."""
    rows = []
    page_size = 500
    offset = 0
    query = query.order("created_at", desc=True).order("id")
    while True:
        page = query.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(page)
        if len(page) < page_size:
            return rows
        offset += page_size
