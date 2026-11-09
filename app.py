from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps
import uuid
import os
import re
from urllib.parse import quote_plus
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import jsonify, request

from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from config import Config
from services.payments import create_wompi_checkout, process_wompi_webhook
from services.supabase_client import get_supabase

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")  # o SUPABASE_SERVICE_ROLE_KEY si la tienes

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Faltan SUPABASE_URL o SUPABASE_KEY en el .env")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    @app.template_filter("money")
    def money_format(value):
        try:
            return "{:,.2f}".format(float(value or 0))
        except Exception:
            return "0.00"

    def now_iso() -> str:
        return datetime.utcnow().isoformat()

    def to_decimal(value, default="0") -> Decimal:
        try:
            return Decimal(str(value if value is not None else default))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal(default)

    def get_user_by_id(user_id: str):
        sb = get_supabase()
        resp = (
            sb.table("users")
            .select("*")
            .eq("id", user_id)
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def get_user_by_email(email: str):
        sb = get_supabase()
        resp = (
            sb.table("users")
            .select("*")
            .eq("email", email.lower().strip())
            .limit(1)
            .execute()
        )
        return resp.data[0] if resp.data else None

    def login_required(view_func):
        @wraps(view_func)
        def wrapped(*args, **kwargs):
            if not session.get("user_id"):
                flash("Debes iniciar sesión para continuar.", "warning")
                return redirect(url_for("login"))
            return view_func(*args, **kwargs)
        return wrapped

    def record_transaction(
        user_id: str,
        kind: str,
        amount: Decimal,
        description: str,
        reference: str | None = None
    ):
        sb = get_supabase()
        sb.table("balance_transactions").insert({
            "user_id": user_id,
            "transaction_type": kind,
            "amount": float(amount),
            "description": description,
            "reference": reference,
            "created_at": now_iso(),
        }).execute()

    def update_user_balance(user_id: str, new_balance: Decimal):
        sb = get_supabase()

        valor_entero = int(new_balance)

        sb.table("users").update({
            "balance": valor_entero,
            "saldo": valor_entero,
            "updated_at": now_iso(),
        }).eq("id", user_id).execute()

    @app.route("/api/reportes-mapa")
    def reportes_mapa():
        if not session.get("user_id"):
            response = jsonify({
                "locked": True,
                "message": "Debes iniciar sesión o registrarte para ver los datos."
            })
            response.status_code = 401
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            return response

        sb = get_supabase()

        limite_panel = request.args.get("limit", 8)

        try:
            limite_panel = int(limite_panel)
        except:
            limite_panel = 8

        if limite_panel <= 0:
            limite_panel = 8

        if limite_panel > 30:
            limite_panel = 30

        # ==========================
        # RANGO DEL DÍA ACTUAL COLOMBIA
        # ==========================
        zona_colombia = ZoneInfo("America/Bogota")
        ahora_colombia = datetime.now(zona_colombia)

        inicio_dia_colombia = ahora_colombia.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

        fin_dia_colombia = inicio_dia_colombia + timedelta(days=1)

        inicio_utc = inicio_dia_colombia.astimezone(timezone.utc)
        fin_utc = fin_dia_colombia.astimezone(timezone.utc)

        inicio_utc_str = inicio_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        fin_utc_str = fin_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        # ==========================
        # 1) TODOS LOS REPORTADOS ACTIVOS
        # Para el mapa y total general
        # ==========================
        resp_todos = sb.table("negative_reports") \
            .select("id, city, department, lat, lng, status, created_at") \
            .eq("status", "activo") \
            .execute()

        todos_rows = resp_todos.data or []

        # ==========================
        # 2) SOLO REPORTES DE HOY
        # Para la tabla derecha de recientes
        # ==========================
        resp_hoy = sb.table("negative_reports") \
            .select("id, city, department, lat, lng, status, created_at") \
            .eq("status", "activo") \
            .gte("created_at", inicio_utc_str) \
            .lt("created_at", fin_utc_str) \
            .order("created_at", desc=True) \
            .execute()

        hoy_rows = resp_hoy.data or []

        def parse_fecha(fecha):
            if not fecha:
                return None

            try:
                return datetime.fromisoformat(str(fecha).replace("Z", "+00:00"))
            except:
                return None

        def limpiar_fila(r):
            city = (r.get("city") or "").strip()
            department = (r.get("department") or "").strip()
            lat = r.get("lat")
            lng = r.get("lng")

            if not city or not department or lat is None or lng is None:
                return None

            try:
                lat_float = float(lat)
                lng_float = float(lng)
            except:
                return None

            return {
                "id": r.get("id"),
                "city": city,
                "department": department,
                "lat": lat_float,
                "lng": lng_float,
                "created_at": r.get("created_at")
            }

        todos_limpios = []
        hoy_limpios = []

        for r in todos_rows:
            fila = limpiar_fila(r)

            if fila:
                todos_limpios.append(fila)

        for r in hoy_rows:
            fila = limpiar_fila(r)

            if fila:
                hoy_limpios.append(fila)

        # ==========================
        # AGRUPAR TODOS POR CIUDAD
        # Esto alimenta el mapa
        # ==========================
        conteo_ciudades = {}
        conteo_departamentos = {}

        for r in todos_limpios:
            city = r["city"]
            department = r["department"]
            lat = r["lat"]
            lng = r["lng"]
            created_at = r["created_at"]

            key_ciudad = f"{department}||{city}"

            if key_ciudad not in conteo_ciudades:
                conteo_ciudades[key_ciudad] = {
                    "city": city,
                    "department": department,
                    "lat": lat,
                    "lng": lng,
                    "total": 0,
                    "abiertos": 0,
                    "reincidentes": 0,
                    "nivel": "Bajo",
                    "ultimo_reporte": created_at
                }

            conteo_ciudades[key_ciudad]["total"] += 1
            conteo_ciudades[key_ciudad]["abiertos"] += 1

            fecha_actual = parse_fecha(created_at)
            fecha_guardada = parse_fecha(conteo_ciudades[key_ciudad].get("ultimo_reporte"))

            if fecha_actual and (not fecha_guardada or fecha_actual > fecha_guardada):
                conteo_ciudades[key_ciudad]["ultimo_reporte"] = created_at

            if department not in conteo_departamentos:
                conteo_departamentos[department] = {
                    "department": department,
                    "total": 0,
                    "cities": [],
                    "ultimos": []
                }

            conteo_departamentos[department]["total"] += 1

        ciudades = list(conteo_ciudades.values())

        for item in ciudades:
            item["reincidentes"] = max(0, item["total"] - 1)

            if item["total"] >= 7:
                item["nivel"] = "Alto"
            elif item["total"] >= 4:
                item["nivel"] = "Medio"
            else:
                item["nivel"] = "Bajo"

        for ciudad in ciudades:
            dept = ciudad["department"]

            if dept in conteo_departamentos:
                conteo_departamentos[dept]["cities"].append(ciudad)

        # ==========================
        # ÚLTIMOS REPORTES DE HOY
        # Esto alimenta solo la tabla derecha
        # ==========================
        ultimos_hoy = []

        for r in hoy_limpios:
            item = {
                "id": r.get("id"),
                "city": r["city"],
                "department": r["department"],
                "lat": r["lat"],
                "lng": r["lng"],
                "total": 1,
                "abiertos": 1,
                "reincidentes": 0,
                "nivel": "Bajo",
                "ultimo_reporte": r.get("created_at")
            }

            ultimos_hoy.append(item)

            dept = r["department"]

            if dept in conteo_departamentos:
                conteo_departamentos[dept]["ultimos"].append(item)

        ultimos_hoy = sorted(
            ultimos_hoy,
            key=lambda x: parse_fecha(x.get("ultimo_reporte")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True
        )[:limite_panel]

        departamentos = list(conteo_departamentos.values())

        departamentos = sorted(
            departamentos,
            key=lambda x: x["total"],
            reverse=True
        )

        for dept in departamentos:
            dept["cities"] = sorted(
                dept["cities"],
                key=lambda x: x["total"],
                reverse=True
            )

            dept["ultimos"] = sorted(
                dept["ultimos"],
                key=lambda x: parse_fecha(x.get("ultimo_reporte")) or datetime.min.replace(tzinfo=timezone.utc),
                reverse=True
            )[:limite_panel]

        response = jsonify({
            "fecha_colombia": inicio_dia_colombia.date().isoformat(),

            # Total general del país
            "total_reportados_pais": len(todos_rows),
            "total_mapeados_pais": len(todos_limpios),
            "total_ciudades_pais": len(ciudades),
            "total_departamentos_pais": len(departamentos),

            # Solo hoy
            "total_reportes_hoy": len(hoy_rows),
            "total_mapeados_hoy": len(hoy_limpios),

            # Mapa
            "departamentos": departamentos,
            "ciudades": ciudades,

            # Tabla derecha
            "ultimos": ultimos_hoy
        })

        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

        return response
        
    def search_person_records(term: str):
        cleaned = str(term or "").strip()
        if not cleaned:
            return []

        # CASO DEMO QUEMADO
        if cleaned == "1004":
            return [{
                "id": "demo-1004",
                "document_number": "1004",
                "full_name": "Juan Sebastián Cárdenas López",
                "city": "Pereira",
                "phone": "3158742210",
                "email": "juan.cardenas.demo@gmail.com"
            }]

        sb = get_supabase()

        if cleaned.isdigit():
            resp = (
                sb.table("people_records")
                .select("*")
                .eq("document_number", cleaned)
                .limit(20)
                .execute()
            )
            return resp.data or []

        resp = (
            sb.table("people_records")
            .select("*")
            .ilike("full_name", f"%{cleaned}%")
            .limit(20)
            .execute()
        )
        return resp.data or []

    def get_negative_reports(document_number: str):
        doc = str(document_number or "").strip()

        # CASO DEMO QUEMADO
        if doc == "1004":
            return [
                {
                    "reason": "No recibió pedido contra entrega",
                    "details": "El cliente confirmó el pedido por WhatsApp, se despachó el producto y al llegar el mensajero al punto de entrega el cliente rechazó la recepción sin justificación.",
                    "city": "Pereira",
                    "phone": "3158742210",
                    "status": "activo",
                    "created_at": "2026-03-20T10:30:00"
                },
                {
                    "reason": "Pérdida logística por devolución",
                    "details": "Se generó devolución del pedido, costo de transporte y afectación operativa al comercio por entrega fallida.",
                    "city": "Pereira",
                    "phone": "3158742210",
                    "status": "activo",
                    "created_at": "2026-03-22T15:45:00"
                }
            ]

        sb = get_supabase()
        resp = (
            sb.table("negative_reports")
            .select("*")
            .eq("target_document", doc)
            .eq("status", "activo")
            .order("created_at", desc=True)
            .execute()
        )
        return resp.data or []

    @app.context_processor
    def inject_globals():
        current_user = get_user_by_id(session.get("user_id")) if session.get("user_id") else None
        wallet_balance = get_wallet_balance(current_user) if current_user else Decimal("0")

        return {
            "app_name": app.config["APP_NAME"],
            "current_user": current_user,
            "query_cost": app.config["QUERY_COST"],
            "wallet_balance": wallet_balance,
        }

    @app.route("/")
    def index():
        features = [
            "Registro e inicio de sesión seguros",
            "Consultas con descuento automático de saldo",
            "Reportes negativos ligados al documento consultado",
            "Historial de movimientos y consumos",
            "Base lista para integrar Wompi y Twilio",
        ]
        public_report_count = 0

        try:
            count_resp = get_supabase().table("negative_reports") \
                .select("id") \
                .eq("status", "activo") \
                .execute()
            public_report_count = len(count_resp.data or [])
        except Exception:
            public_report_count = 0

        return render_template(
            "index.html",
            features=features,
            public_report_count=public_report_count
        )

    DOGON_ADMIN_WHATSAPP = os.getenv("DOGON_ADMIN_WHATSAPP", "573145855142")


    def normalize_whatsapp(number: str) -> str:
        return "".join(ch for ch in str(number) if ch.isdigit())


    def get_user_by_email(email):
        res = supabase.table("users").select("*").eq("email", email).limit(1).execute()
        return res.data[0] if res.data else None


    def get_user_by_id(user_id):
        res = supabase.table("users").select("*").eq("id", user_id).limit(1).execute()
        return res.data[0] if res.data else None


    def get_user_by_pending_token(token):
        res = supabase.table("users").select("*").eq("pending_token", token).limit(1).execute()
        return res.data[0] if res.data else None


    def get_recarga_by_id(recarga_id):
        res = supabase.table("recargas").select("*").eq("id", recarga_id).limit(1).execute()
        return res.data[0] if res.data else None


    def get_pending_recharge_for_user(user_id):
        res = (
            supabase.table("recargas")
            .select("*")
            .eq("user_id", user_id)
            .eq("estado", "pendiente")
            .order("id", desc=True)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None


    def build_whatsapp_url(user, amount=8000):
        admin_number = normalize_whatsapp(DOGON_ADMIN_WHATSAPP)

        mensaje = (
            "Hola, deseo confirmar mi depósito para activar mi cuenta en Dogon.%0A%0A"
            f"Nombre: {user.get('full_name', '')}%0A"
            f"Correo: {user.get('email', '')}%0A"
            f"Teléfono: {user.get('phone', '') or 'No registrado'}%0A"
            f"Usuario ID: {user.get('id', '')}%0A"
            f"Valor consignado: ${amount:,.0f}%0A%0A"
            "Indicame los datos para recargar y adjuntaré el comprobante."
        )
        return f"https://wa.me/{admin_number}?text={mensaje}"


    def admin_required(view_func):
        @wraps(view_func)
        def wrapper(*args, **kwargs):
            if not session.get("user_id"):
                flash("Debes iniciar sesión.", "warning")
                return redirect(url_for("login"))

            if session.get("rol") != "admin":
                flash("No tienes permisos para acceder a esta sección.", "danger")
                return redirect(url_for("index"))

            return view_func(*args, **kwargs)
        return wrapper


    # =========================================================
    # REGISTRO
    # =========================================================
    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()
            confirm_password = request.form.get("confirm_password", "").strip()

            if not full_name or not email or not password or not confirm_password:
                flash("Completa todos los campos obligatorios.", "warning")
                return render_template("auth/register.html")

            if password != confirm_password:
                flash("Las contraseñas no coinciden.", "warning")
                return render_template("auth/register.html")

            existing_user = get_user_by_email(email)
            if existing_user:
                flash("Este correo ya se encuentra registrado.", "warning")
                return render_template("auth/register.html")

            pending_token = str(uuid.uuid4())

            user_payload = {
                "full_name": full_name,
                "phone": phone,
                "email": email,
                "password_hash": generate_password_hash(password),
                "rol": "usuario",
                "activo": False,
                "estado_cuenta": "pendiente_pago",
                "saldo": 0,
                "pending_token": pending_token
            }

            try:
                user_insert = supabase.table("users").insert(user_payload).execute()

                if not user_insert.data:
                    flash("No fue posible crear el usuario.", "danger")
                    return render_template("auth/register.html")

                user = user_insert.data[0]

                recharge_payload = {
                    "user_id": user["id"],
                    "valor": 8000,
                    "tipo": "recarga_inicial",
                    "estado": "pendiente",
                    "observacion": "Recarga inicial pendiente por confirmar"
                }

                recharge_insert = supabase.table("recargas").insert(recharge_payload).execute()

                if not recharge_insert.data:
                    supabase.table("users").delete().eq("id", user["id"]).execute()
                    flash("No fue posible iniciar el proceso de recarga.", "danger")
                    return render_template("auth/register.html")

                flash("Usuario creado correctamente. Ahora confirma tu depósito.", "success")
                return redirect(url_for("registro_pendiente_pago", token=pending_token))

            except Exception as e:
                flash(f"Ocurrió un error al registrar: {str(e)}", "danger")
                return render_template("auth/register.html")

        return render_template("auth/register.html")


    # =========================================================
    # PANTALLA PENDIENTE DE PAGO
    # =========================================================
    @app.route("/registro/pendiente/<token>")
    def registro_pendiente_pago(token):
        user = get_user_by_pending_token(token)

        if not user:
            flash("No encontramos el proceso de registro.", "warning")
            return redirect(url_for("register"))

        recarga = get_pending_recharge_for_user(user["id"])
        whatsapp_url = build_whatsapp_url(user, amount=8000)

        return render_template(
            "registro_pendiente_pago.html",
            user=user,
            recarga=recarga,
            whatsapp_url=whatsapp_url
        )


    # =========================================================
    # LOGIN
    # =========================================================
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "").strip()

            user = get_user_by_email(email)

            if not user or not user.get("password_hash") or not check_password_hash(user["password_hash"], password):
                flash("Credenciales inválidas.", "danger")
                return render_template("auth/login.html")

            if not user.get("activo") or user.get("estado_cuenta") != "activo":
                flash("Tu cuenta aún está pendiente por confirmación de pago.", "warning")
                return redirect(url_for("registro_pendiente_pago", token=user["pending_token"]))

            session["user_id"] = user["id"]
            session["user_name"] = user.get("full_name")
            session["rol"] = user.get("rol", "usuario")

            flash("Bienvenido a Dogon.", "success")
            return redirect(url_for("index"))

        return render_template("auth/login.html")

    # =========================================================
    # ADMIN - VER RECARGAS PENDIENTES + HISTORIAL DE APROBACIONES
    # =========================================================
    @app.route("/admin/recargas/pendientes")
    def admin_recargas_pendientes():
        # Recargas pendientes
        recargas_pendientes_res = (
            supabase.table("recargas")
            .select("*")
            .eq("estado", "pendiente")
            .order("created_at", desc=False)
            .execute()
        )

        recargas_pendientes = recargas_pendientes_res.data or []

        # Historial de aprobaciones
        recargas_aprobadas_res = (
            supabase.table("recargas")
            .select("*")
            .eq("estado", "aprobado")
            .order("approved_at", desc=True)
            .execute()
        )

        recargas_aprobadas = recargas_aprobadas_res.data or []

        # Recolectar ids de usuarios y admins para mapear nombres
        user_ids = set()
        admin_ids = set()

        for item in recargas_pendientes:
            if item.get("user_id"):
                user_ids.add(item["user_id"])

        for item in recargas_aprobadas:
            if item.get("user_id"):
                user_ids.add(item["user_id"])
            if item.get("approved_by"):
                admin_ids.add(item["approved_by"])

        ids_a_buscar = list(user_ids.union(admin_ids))

        users_map = {}
        if ids_a_buscar:
            users_res = (
                supabase.table("users")
                .select("id, full_name, email, phone, saldo, activo, estado_cuenta")
                .in_("id", ids_a_buscar)
                .execute()
            )
            users_map = {u["id"]: u for u in (users_res.data or [])}

        # Armar pendientes
        items = []
        for recarga in recargas_pendientes:
            items.append({
                **recarga,
                "user": users_map.get(recarga["user_id"])
            })

        # Armar historial
        historial_aprobaciones = []
        for recarga in recargas_aprobadas:
            historial_aprobaciones.append({
                **recarga,
                "user": users_map.get(recarga["user_id"]),
                "approved_by_user": users_map.get(recarga.get("approved_by"))
            })

        return render_template(
            "admin_recargas_pendientes.html",
            items=items,
            historial_aprobaciones=historial_aprobaciones
        )


    # =========================================================
    # ADMIN - APROBAR RECARGA
    # =========================================================
    @app.route("/admin/recargas/<int:recarga_id>/aprobar", methods=["POST"])
    def aprobar_recarga(recarga_id):
        recarga = get_recarga_by_id(recarga_id)

        if not recarga:
            flash("Recarga no encontrada.", "warning")
            return redirect(url_for("admin_recargas_pendientes"))

        if recarga["estado"] != "pendiente":
            flash("Esta recarga ya fue procesada.", "warning")
            return redirect(url_for("admin_recargas_pendientes"))

        user = get_user_by_id(recarga["user_id"])
        if not user:
            flash("Usuario no encontrado.", "warning")
            return redirect(url_for("admin_recargas_pendientes"))

        try:
            valor_pendiente = int(recarga.get("valor") or 0)
            saldo_actual = int(user.get("saldo") or user.get("balance") or 0)
            nuevo_saldo = saldo_actual + valor_pendiente

            # 1. Actualizar saldo del usuario
            user_update = (
                supabase.table("users")
                .update({
                    "saldo": nuevo_saldo,
                    "balance": nuevo_saldo,   # compatibilidad temporal
                    "activo": True,
                    "estado_cuenta": "activo"
                })
                .eq("id", user["id"])
                .execute()
            )

            if not user_update.data:
                raise Exception("No fue posible actualizar el saldo del usuario.")

            # 2. Marcar recarga como aprobada
            recarga_update = (
                supabase.table("recargas")
                .update({
                    "estado": "aprobado",
                    "approved_by": session.get("user_id"),
                    "approved_at": datetime.utcnow().isoformat(),
                    "observacion": f"Recarga aprobada. Valor abonado: {valor_pendiente}"
                })
                .eq("id", recarga_id)
                .execute()
            )

            if not recarga_update.data:
                raise Exception("No fue posible marcar la recarga como aprobada.")

            # 3. Registrar movimiento en historial
            tx_insert = (
                supabase.table("balance_transactions")
                .insert({
                    "user_id": user["id"],
                    "amount": valor_pendiente,
                    "transaction_type": "recharge_approved",
                    "description": "Recarga aprobada",
                    "reference": f"recarga_{recarga_id}"
                })
                .execute()
            )

            if not tx_insert.data:
                raise Exception("No fue posible registrar el movimiento de saldo.")

            flash(
                f"Recarga aprobada correctamente. Se abonaron ${valor_pendiente:,.0f} a {user['full_name']}.",
                "success"
            )
            return redirect(url_for("admin_recargas_pendientes"))

        except Exception as e:
            flash(f"No fue posible aprobar la recarga: {str(e)}", "danger")
            return redirect(url_for("admin_recargas_pendientes"))

    # =========================================================
    # ADMIN - RECHAZAR RECARGA
    # =========================================================
    @app.route("/admin/recargas/<int:recarga_id>/rechazar", methods=["POST"])
    def rechazar_recarga(recarga_id):
        recarga = get_recarga_by_id(recarga_id)

        if not recarga:
            flash("Recarga no encontrada.", "warning")
            return redirect(url_for("admin_recargas_pendientes"))

        if recarga["estado"] != "pendiente":
            flash("Esta recarga ya fue procesada.", "warning")
            return redirect(url_for("admin_recargas_pendientes"))

        user = get_user_by_id(recarga["user_id"])
        if not user:
            flash("Usuario no encontrado.", "warning")
            return redirect(url_for("admin_recargas_pendientes"))

        try:
            supabase.table("recargas").update({
                "estado": "rechazado",
                "approved_by": session.get("user_id"),
                "rejected_at": datetime.utcnow().isoformat(),
                "observacion": "Recarga rechazada por admin"
            }).eq("id", recarga_id).execute()

            supabase.table("users").update({
                "activo": False,
                "estado_cuenta": "pendiente_pago"
            }).eq("id", user["id"]).execute()

            flash(f"Recarga rechazada para {user['full_name']}.", "warning")
            return redirect(url_for("admin_recargas_pendientes"))

        except Exception as e:
            flash(f"No fue posible rechazar la recarga: {str(e)}", "danger")
            return redirect(url_for("admin_recargas_pendientes"))


    @app.route("/logout")
    def logout():
        session.clear()
        flash("Sesión cerrada correctamente.", "info")
        return redirect(url_for("index"))

    def get_wallet_balance(user):
        if not user:
            return Decimal("0")

        saldo_val = user.get("saldo")
        balance_val = user.get("balance")

        if saldo_val not in (None, ""):
            return to_decimal(saldo_val)

        if balance_val not in (None, ""):
            return to_decimal(balance_val)

        return Decimal("0")

    @app.route("/dashboard")
    @login_required
    def dashboard():
        user = get_user_by_id(session["user_id"])
        sb = get_supabase()

        tx_resp = (
            sb.table("balance_transactions")
            .select("*")
            .eq("user_id", user["id"])
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        query_resp = (
            sb.table("query_history")
            .select("*")
            .eq("user_id", user["id"])
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )
        report_resp = (
            sb.table("negative_reports")
            .select("*")
            .eq("created_by", user["id"])
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        stats = {
            "balance": get_wallet_balance(user),
            "recent_transactions": tx_resp.data or [],
            "recent_queries": query_resp.data or [],
            "recent_reports": report_resp.data or [],
        }

        return render_template("dashboard.html", stats=stats)

    @app.route("/perfil", methods=["GET", "POST"])
    @login_required
    def profile():
        user = get_user_by_id(session["user_id"])
        if request.method == "POST":
            full_name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            new_password = request.form.get("new_password", "").strip()

            payload = {
                "full_name": full_name,
                "phone": phone,
                "updated_at": now_iso(),
            }

            if new_password:
                if len(new_password) < 8:
                    flash("La nueva contraseña debe tener al menos 8 caracteres.", "danger")
                    return render_template("profile.html", user=user)
                payload["password_hash"] = generate_password_hash(new_password)

            get_supabase().table("users").update(payload).eq("id", user["id"]).execute()
            flash("Perfil actualizado.", "success")
            return redirect(url_for("profile"))

        return render_template("profile.html", user=user)

    
    # =========================================================
    # WALLET / SALDO
    # =========================================================
    @app.route("/wallet")
    @login_required
    def wallet():
        user = get_user_by_id(session["user_id"])
        sb = get_supabase()

        tx_resp = (
            sb.table("balance_transactions")
            .select("*")
            .eq("user_id", user["id"])
            .order("created_at", desc=True)
            .execute()
        )

        pending_resp = (
            sb.table("recargas")
            .select("*")
            .eq("user_id", user["id"])
            .eq("estado", "pendiente")
            .order("created_at", desc=True)
            .execute()
        )

        transactions = tx_resp.data or []
        pending_recharges = pending_resp.data or []

        return render_template(
            "wallet.html",
            user=user,
            wallet_balance=get_wallet_balance(user),
            transactions=transactions,
            pending_recharges=pending_recharges
        )


    # =========================================================
    # USUARIO - SOLICITAR RECARGA DE SALDO
    # =========================================================
    @app.route("/wallet/solicitar-recarga", methods=["POST"])
    @login_required
    def solicitar_recarga_wallet():
        user = get_user_by_id(session["user_id"])
        sb = get_supabase()

        amount_raw = request.form.get("amount", "").strip().replace(",", "")

        try:
            amount = int(float(amount_raw))
        except Exception:
            flash("Ingresa un valor válido para la recarga.", "warning")
            return redirect(url_for("wallet"))

        if amount < 5000:
            flash("La recarga mínima es de $5.000.", "warning")
            return redirect(url_for("wallet"))

        try:
            # Si ya tiene una pendiente, reutilizamos esa vista
            pending_resp = (
                sb.table("recargas")
                .select("*")
                .eq("user_id", user["id"])
                .eq("estado", "pendiente")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )

            if pending_resp.data:
                recarga_pendiente = pending_resp.data[0]
                flash("Ya tienes una solicitud de recarga pendiente por confirmar.", "warning")
                return redirect(url_for("wallet_recarga_pendiente", recarga_id=recarga_pendiente["id"]))

            payload = {
                "user_id": user["id"],
                "valor": amount,
                "tipo": "recarga_manual_whatsapp",
                "estado": "pendiente",
                "observacion": f"Solicitud de recarga por WhatsApp por valor de {amount}"
            }

            insert_resp = sb.table("recargas").insert(payload).execute()

            if not insert_resp.data:
                flash("No fue posible crear la solicitud de recarga.", "danger")
                return redirect(url_for("wallet"))

            recarga = insert_resp.data[0]

            flash("Solicitud de recarga creada correctamente. Ahora confirma por WhatsApp.", "success")
            return redirect(url_for("wallet_recarga_pendiente", recarga_id=recarga["id"]))

        except Exception as e:
            flash(f"No fue posible crear la solicitud: {str(e)}", "danger")
            return redirect(url_for("wallet"))


    # =========================================================
    # USUARIO - VISTA DE RECARGA PENDIENTE
    # =========================================================
    @app.route("/wallet/recarga/<int:recarga_id>/pendiente")
    @login_required
    def wallet_recarga_pendiente(recarga_id):
        user = get_user_by_id(session["user_id"])
        recarga = get_recarga_by_id(recarga_id)

        if not recarga or recarga["user_id"] != user["id"]:
            flash("Solicitud no encontrada.", "warning")
            return redirect(url_for("wallet"))

        admin_phone = "573000000000"  # <-- CAMBIA ESTE NÚMERO

        mensaje = (
            f"Hola, quiero confirmar una recarga de saldo.%0A"
            f"Usuario: {user.get('full_name', '')}%0A"
            f"Correo: {user.get('email', '')}%0A"
            f"Valor: ${int(recarga.get('valor') or 0):,}%0A"
            f"Solicitud ID: {recarga.get('id')}"
        )

        whatsapp_url = f"https://wa.me/{admin_phone}?text={mensaje}"

        return render_template(
            "wallet_recarga_pendiente.html",
            user=user,
            recarga=recarga,
            whatsapp_url=whatsapp_url
        )

    @app.route("/saldo/recarga-demo", methods=["POST"])
    @login_required
    def recharge_demo():
        user = get_user_by_id(session["user_id"])
        amount = to_decimal(request.form.get("amount", "0"))

        if amount < Decimal(str(app.config["RECHARGE_MIN_AMOUNT"])):
            flash(
                f"La recarga mínima es de ${app.config['RECHARGE_MIN_AMOUNT']:,.0f} COP.",
                "danger"
            )
            return redirect(url_for("wallet"))

        new_balance = get_wallet_balance(user) + amount
        update_user_balance(user["id"], new_balance)
        record_transaction(
            user["id"],
            "recarga_demo",
            amount,
            "Recarga demo acreditada manualmente",
            reference=f"DEMO-{uuid.uuid4().hex[:8].upper()}"
        )
        flash("Recarga demo aplicada correctamente.", "success")
        return redirect(url_for("wallet"))

    @app.route("/saldo/wompi-checkout", methods=["POST"])
    @login_required
    def wompi_checkout():
        amount = to_decimal(request.form.get("amount", "0"))
        checkout = create_wompi_checkout(session["user_id"], float(amount))
        flash(checkout["message"], "info")
        return redirect(url_for("wallet"))

    @app.route("/webhooks/wompi", methods=["POST"])
    def wompi_webhook():
        result = process_wompi_webhook(request.get_json(silent=True) or {})
        return jsonify(result)

    @app.route("/reportados/gratis", methods=["GET", "POST"])
    def free_report_lookup():
        lookup_type = request.form.get("lookup_type", "phone")
        lookup_value = request.form.get("lookup_value", "").strip()
        signal_count = None
        error = None

        if request.method == "POST":
            if lookup_type not in ("phone", "document") or not re.fullmatch(r"[0-9]{5,20}", lookup_value):
                error = "Ingresa el número completo, solo con dígitos."
            else:
                try:
                    column = "phone" if lookup_type == "phone" else "target_document"
                    result = (get_supabase().table("negative_reports")
                              .select("id", count="exact")
                              .eq("status", "activo")
                              .eq(column, lookup_value)
                              .limit(1).execute())
                    if result.count is None:
                        raise ValueError("Report count unavailable")
                    signal_count = result.count
                except Exception:
                    app.logger.warning("No se pudo completar la consulta gratuita de reportados.")
                    error = "No fue posible realizar la consulta. Intenta de nuevo."

        response = app.make_response(render_template(
            "free_report_lookup.html", lookup_type=lookup_type, lookup_value=lookup_value,
            signal_count=signal_count, error=error,
        ))
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.route("/consultas", methods=["GET", "POST"])
    @login_required
    def queries():
        user = get_user_by_id(session["user_id"])
        results = []
        search_term = ""
        search_filters = {
            "document": "",
            "phone": "",
            "full_name": "",
        }
        attached_reports = {}
        query_cost = Decimal(str(app.config["QUERY_COST"]))

        if request.method == "POST":
            search_filters = {
                "document": str(request.form.get("document", "")).strip(),
                "phone": str(request.form.get("phone", "")).strip(),
                "full_name": str(request.form.get("full_name", "") or request.form.get("term", "")).strip(),
            }
            active_filters = {key: value for key, value in search_filters.items() if value}
            search_term = " | ".join(active_filters.values())

            if not active_filters:
                flash("Ingresa al menos un filtro para consultar.", "danger")
                return render_template(
                    "queries.html",
                    results=results,
                    search_term=search_term,
                    search_filters=search_filters,
                    attached_reports=attached_reports,
                    query_cost=query_cost
                )

            current_balance = get_wallet_balance(user)

            if current_balance < query_cost:
                flash("No tienes saldo suficiente para realizar la consulta.", "warning")
                return redirect(url_for("wallet"))

            supabase = get_supabase()

            reports_query = supabase.table("negative_reports") \
                .select("id, target_document, target_name, phone, address, city, reason, details, status, created_at") \
                .eq("status", "activo")

            if search_filters["document"]:
                reports_query = reports_query.ilike("target_document", f"%{search_filters['document']}%")

            if search_filters["phone"]:
                reports_query = reports_query.ilike("phone", f"%{search_filters['phone']}%")

            if search_filters["full_name"]:
                reports_query = reports_query.ilike("target_name", f"%{search_filters['full_name']}%")

            reports_resp = reports_query.order("created_at", desc=True).execute()

            reports_found = reports_resp.data or []

            # 💸 Descontar saldo por la consulta
            new_balance = current_balance - query_cost
            update_user_balance(user["id"], new_balance)

            record_transaction(
                user["id"],
                "consulta",
                -query_cost,
                f"Descuento por consulta de reportes negativos: {search_term}"
            )

            grouped = {}

            for report in reports_found:
                document_number = (report.get("target_document") or "").strip()
                report_name = (report.get("target_name") or "").strip()
                report_phone = (report.get("phone") or "").strip()
                key = document_number.lower() or f"{report_name.lower()}|{report_phone}"

                if not key:
                    continue

                if key not in grouped:
                    grouped[key] = {
                        "lookup_key": key,
                        "full_name": report_name or "No registrado",
                        "document_number": document_number or "No registrado",
                        "city": report.get("city") or "Sin ciudad",
                        "phone": report.get("phone") or "Sin teléfono",
                        "email": "No registrado",
                        "address": report.get("address") or "Sin dirección",
                    }

                    attached_reports[key] = []

                attached_reports[key].append(report)

            results = list(grouped.values())

            supabase.table("query_history").insert({
                "user_id": user["id"],
                "search_term": search_term or "Consulta con filtros",
                "cost": float(query_cost),
                "result_count": len(results),
                "created_at": now_iso(),
            }).execute()

            if results:
                flash("Consulta realizada correctamente.", "success")
            else:
                flash("El usuario no se encuentra reportado en nuestra BD.", "info")

            # refrescar user para que si en esta misma vista lo usas, ya venga actualizado
            user = get_user_by_id(session["user_id"])

        return render_template(
            "queries.html",
            results=results,
            search_term=search_term,
            search_filters=search_filters,
            attached_reports=attached_reports,
            query_cost=query_cost
        )
    @app.route("/negative-reports", methods=["GET", "POST"])
    def negative_reports():

        if "user_id" not in session:
            return redirect(url_for("login"))

        error = None
        success = None
        form_data = {
            "target_name": "",
            "phone": "",
            "address": "",
            "department": "",
            "city": "",
            "reason": "",
            "details": "",
            "lat": "",
            "lng": ""
        }

        if request.method == "POST":
            target_name = (request.form.get("target_name") or "").strip()
            phone = (request.form.get("phone") or "").strip()
            address = (request.form.get("address") or "").strip()
            department = (request.form.get("department") or "").strip()
            city = (request.form.get("city") or "").strip()
            reason = (request.form.get("reason") or "").strip()
            details = (request.form.get("details") or "").strip()
            lat_raw = (request.form.get("lat") or "").strip()
            lng_raw = (request.form.get("lng") or "").strip()

            print("DEBUG department:", department)
            print("DEBUG city:", city)
            print("DEBUG lat_raw:", lat_raw)
            print("DEBUG lng_raw:", lng_raw)

            lat = None
            lng = None

            try:
                if lat_raw and lat_raw not in ["undefined", "null"]:
                    lat = float(lat_raw)
                if lng_raw and lng_raw not in ["undefined", "null"]:
                    lng = float(lng_raw)
            except ValueError:
                lat = None
                lng = None

            form_data = {
                "target_name": target_name,
                "phone": phone,
                "address": address,
                "department": department,
                "city": city,
                "reason": reason,
                "details": details,
                "lat": lat_raw,
                "lng": lng_raw
            }

            if not target_name or not phone or not address or not department or not city or not reason:
                error = "Todos los campos obligatorios deben estar completos."
            else:
                payload = {
                    "target_document": None,
                    "target_name": target_name,
                    "phone": phone,
                    "address": address,
                    "department": department,
                    "city": city,
                    "reason": reason,
                    "details": details,
                    "lat": lat,
                    "lng": lng,
                    "status": "activo",
                    "created_by": session["user_id"]
                }

                print("DEBUG payload:", payload)

                resp = supabase.table("negative_reports").insert(payload).execute()

                if getattr(resp, "data", None):
                    success = "Reporte registrado correctamente."
                    form_data = {
                        "target_name": "",
                        "phone": "",
                        "address": "",
                        "department": "",
                        "city": "",
                        "reason": "",
                        "details": "",
                        "lat": "",
                        "lng": ""
                    }
                else:
                    error = "No fue posible guardar el reporte."

        reports_resp = supabase.table("negative_reports") \
            .select("id, target_name, phone, address, department, city, reason, details, status, created_at") \
            .order("created_at", desc=True) \
            .execute()

        reports = reports_resp.data or []

        return render_template(
            "negative_reports.html",
            reports=reports,
            error=error,
            success=success,
            form_data=form_data
        )
    @app.route("/health")
    def health():
        return jsonify({"ok": True, "app": app.config["APP_NAME"]})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
