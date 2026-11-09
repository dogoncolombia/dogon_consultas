# ConsultaPlus - Flask + Supabase

Aplicación web moderna para una plataforma de consultas con autenticación, saldo, historial de consumos y reportes negativos.

## Incluye
- Landing pública moderna
- Registro e inicio de sesión
- Dashboard privado
- Perfil básico
- Saldo y movimientos
- Recarga demo lista para reemplazar por Wompi
- Módulo de consultas con descuento automático de saldo
- Módulo de reportes negativos
- Estructura escalable para integrar APIs después

## Estructura
```
consulta_app/
├── app.py
├── config.py
├── requirements.txt
├── schema.sql
├── .env.example
├── services/
│   ├── notifications.py
│   ├── payments.py
│   └── supabase_client.py
├── static/
│   ├── css/app.css
│   └── js/app.js
└── templates/
    ├── base.html
    ├── index.html
    ├── dashboard.html
    ├── profile.html
    ├── wallet.html
    ├── queries.html
    ├── negative_reports.html
    └── auth/
        ├── login.html
        └── register.html
```

## Instalación
Para reconstruir una base perdida, consulta primero
[RECONSTRUIR_BASE_DATOS.md](RECONSTRUIR_BASE_DATOS.md). El `schema.sql` actualizado
crea las seis tablas que utiliza `app.py`, sin insertar datos demo. El backend
requiere `SUPABASE_KEY` con la clave `service_role`; una clave pública no tendrá
acceso a estas tablas. Los registros perdidos requieren un respaldo para recuperarse.

1. Crea un entorno virtual.
2. Instala dependencias:
   ```bash
   pip install -r requirements.txt
   ```
3. Configura `.env` siguiendo `RECONSTRUIR_BASE_DATOS.md` (URL, clave de servidor y secreto de sesión).
4. Ejecuta `schema.sql` en Supabase.
5. Inicia la aplicación:
   ```bash
   python app.py
   ```
6. Abre `http://127.0.0.1:5000`

## Flujo recomendado
- Registra un usuario
- Activa tu cuenta administradora siguiendo `RECONSTRUIR_BASE_DATOS.md`
- Confirma y aprueba una recarga real
- Ingresa al dashboard
- Ejecuta consultas por documento o nombre
- Registra reportes negativos

## Integraciones futuras
### Wompi
La ruta `/saldo/wompi-checkout` y `/webhooks/wompi` ya están preparadas como stub.

### Twilio
El servicio `services/notifications.py` quedó creado para conectar alertas después.

## Mejoras sugeridas
- Migrar autenticación a Supabase Auth
- Agregar CSRF con Flask-WTF
- Crear RPC transaccional en Supabase para descontar saldo sin riesgo de concurrencia
- Añadir roles (admin, operador, supervisor)
- Registrar resultados completos de consultas en una tabla dedicada
