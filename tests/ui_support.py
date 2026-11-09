"""Offline data for UI regression checks. Never opens the production database."""
from copy import deepcopy
import importlib.util
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def report(index, name="Cliente de prueba", phone="3001234567", document="123456"):
    return dict(id=f"report-{index:06}", target_document=document, target_name=name,
                phone=phone, address="Dirección de prueba", department="ANTIOQUIA",
                city="MEDELLÍN", lat=6.2442, lng=-75.5812, reason="Entrega no recibida",
                details="Registro ficticio para verificar la interfaz.", status="activo",
                created_by="test-user", created_at="2026-11-09T15:00:00+00:00")


class Database:
    def __init__(self):
        self.tables = {
            "users": [dict(id="test-user", full_name="María Comercio", email="prueba@example.test",
                           phone="3001234567", balance=8000, saldo=8000, activo=True,
                           is_active=True, estado_cuenta="activo", rol="admin", pending_token="test-token")],
            "negative_reports": [report(i) for i in range(3)],
            "balance_transactions": [dict(id="tx-1", user_id="test-user", amount=8000,
                                          transaction_type="recarga", description="Recarga de prueba",
                                          reference="TEST-001", created_at="2026-11-09T14:00:00+00:00")],
            "query_history": [],
            "recargas": [dict(id=1, user_id="test-user", valor=8000, tipo="saldo", estado="pendiente",
                              observacion="Solicitud de prueba", created_at="2026-11-09T14:00:00+00:00")],
            "people_records": [],
        }

    def table(self, name):
        return Query(self, name)


class Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.filters, self.orders = [], []
        self.start, self.end, self.maximum = 0, None, None
        self.mode, self.payload = "select", None
        self.with_count = False

    def select(self, *args, **kwargs):
        self.with_count = kwargs.get("count") == "exact"
        return self

    def eq(self, key, value):
        self.filters.append(lambda row: row.get(key) == value)
        return self

    def ilike(self, key, value):
        needle = value.strip("%").casefold()
        self.filters.append(lambda row: needle in str(row.get(key) or "").casefold())
        return self

    def in_(self, key, values):
        self.filters.append(lambda row: row.get(key) in values)
        return self

    def gte(self, key, value):
        self.filters.append(lambda row: str(row.get(key) or "") >= value)
        return self

    def lt(self, key, value):
        self.filters.append(lambda row: str(row.get(key) or "") < value)
        return self

    def order(self, key, desc=False):
        self.orders.append((key, desc))
        return self

    def limit(self, count):
        self.maximum = count
        return self

    def range(self, start, end):
        self.start, self.end = start, end
        return self

    def insert(self, payload):
        self.mode, self.payload = "insert", payload
        return self

    def update(self, payload):
        self.mode, self.payload = "update", payload
        return self

    def execute(self):
        rows = [r for r in self.db.tables[self.name] if all(f(r) for f in self.filters)]
        total = len(rows)
        if self.mode == "insert":
            self.db.tables[self.name].append(deepcopy(self.payload))
            return SimpleNamespace(data=[deepcopy(self.payload)])
        if self.mode == "update":
            for row in rows:
                row.update(self.payload)
        for key, desc in reversed(self.orders):
            rows.sort(key=lambda row: str(row.get(key) or ""), reverse=desc)
        rows = rows[self.start:self.end + 1 if self.end is not None else None]
        if self.maximum is not None:
            rows = rows[:self.maximum]
        return SimpleNamespace(data=deepcopy(rows), count=total if self.with_count else None)


def make_app(db):
    # The module creates a client during import: replace the factory before loading.
    os.environ.setdefault("SUPABASE_URL", "https://offline.example.test")
    os.environ.setdefault("SUPABASE_KEY", "offline-test-key")
    with patch("supabase.create_client", return_value=db):
        spec = importlib.util.spec_from_file_location("offline_ui_app", ROOT / "app.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    module.get_supabase = lambda: db
    module.supabase = db
    module.app.config.update(TESTING=True, SECRET_KEY="offline-ui-test", QUERY_COST=400)
    return module.app
