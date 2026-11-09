# Dogon en Render para pruebas

La aplicación es Flask: en Render se crea como **Web Service**, con Python.
La pantalla **Static Site** no ejecuta `app.py`.

## 1. Preparar el repositorio

Sube el proyecto a un repositorio privado de GitHub y conéctalo a Render.
Incluye `app.py`, `config.py`, `services/`, `templates/`, `static/`,
`requirements.txt`, `.python-version` y `.gitignore`.
También puedes incluir `render.yaml` y la documentación.

No subas `.env`. Las credenciales se introducen en Render > Environment.
`.env.example` contiene únicamente marcadores de ejemplo.

## 2. Crear el servicio

En Render selecciona **New > Web Service**, conecta GitHub y elige el repositorio.

| Campo | Valor |
| --- | --- |
| Name | `dogon-pruebas` |
| Language | Python 3 |
| Branch | La rama que contiene estos cambios |
| Root Directory | Vacío, si `app.py` está en la raíz del repositorio |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn --bind 0.0.0.0:$PORT --workers 1 app:app` |
| Instance Type | Free |
| Health Check Path | `/health` |
| Auto-Deploy | Off, para controlar las actualizaciones durante las pruebas |

`.python-version` selecciona la versión 3.11 más reciente disponible en Render.
No hace falta configurar `PYTHON_VERSION` por separado.

## 3. Variables de entorno

| Variable | Valor |
| --- | --- |
| `SUPABASE_URL` | URL del proyecto Supabase elegido para pruebas |
| `SUPABASE_KEY` | Clave `service_role` de ese mismo proyecto, solo en el servidor |
| `SECRET_KEY` | Secreto aleatorio estable; usa Generate en Render si está disponible |
| `SESSION_COOKIE_SECURE` | `true` |
| `FLASK_DEBUG` | `0` |

Para generar un secreto en tu equipo: `python -c "import secrets; print(secrets.token_hex(32))"`.
Pega el resultado directamente en Render, sin publicarlo en GitHub.

Puedes conservar `APP_NAME`, `QUERY_COST`, `RECHARGE_MIN_AMOUNT` y
`DOGON_ADMIN_WHATSAPP` de tu configuración actual si los necesitas.

## 4. Datos de prueba

Un servicio Free no convierte las operaciones de la aplicación en simulaciones.
Las altas, los reportes y las recargas aprobadas escriben en el Supabase configurado.
Usa un proyecto Supabase de pruebas separado y ejecuta allí `schema.sql` una vez.
Sigue `RECONSTRUIR_BASE_DATOS.md` para crear una cuenta y asignarle administración.
El proyecto nuevo no recupera los datos de tu base actual.

No uses `tests/preview_ui.py` para este despliegue: es una herramienta local con
datos ficticios y acceso de sesión simplificado para revisar el diseño.
El arranque en Render es `app:app`, sin el depurador de Flask.

Antes de abrir el servicio a usuarios reales, deben revisarse los permisos
de administración y los flujos de pago. Esta configuración prepara el alojamiento
de pruebas; no declara la aplicación lista para producción.

## 5. Desplegar y verificar

Pulsa **Deploy Web Service**. Al terminar, comprueba `/health` en la URL
`https://NOMBRE.onrender.com` y después prueba registro, acceso y consulta
usando únicamente datos de prueba.

El plan Free puede suspender el servicio tras 15 minutos sin tráfico; el primer
acceso después puede tardar aproximadamente un minuto.

## Alternativa con Blueprint

Con el repositorio ya conectado, **New > Blueprint** puede importar `render.yaml`.
Render genera `SECRET_KEY` y pide los valores de Supabase.
No incluyas claves reales dentro de `render.yaml`.

Fuentes: [Flask en Render](https://render.com/docs/deploy-flask),
[Python](https://render.com/docs/python-version),
[plan Free](https://render.com/docs/free),
[Blueprints](https://render.com/docs/blueprint-spec).
