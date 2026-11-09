# Reconstrucción de la base de datos Dogon

## Archivo que debes ejecutar

Usa **`schema.sql`**, en el SQL Editor del proyecto Supabase, seleccionando el
rol `postgres`. Ejecuta el archivo completo, desde `begin` hasta `commit`.
No necesitas ejecutar `CREATE DATABASE`: el proyecto Supabase ya tiene su base.

El script crea estas seis tablas en `public`:

| Tabla | Uso en el proyecto |
| --- | --- |
| `users` | Registro, contraseñas con hash de Werkzeug, perfil, rol, activación y saldo |
| `recargas` | Solicitudes iniciales y manuales, aprobación y rechazo |
| `balance_transactions` | Movimientos de saldo, incluidos débitos negativos |
| `query_history` | Consultas realizadas, costo y cantidad de resultados |
| `negative_reports` | Reportados, teléfono, dirección, ubicación y coordenadas del mapa |
| `people_records` | Búsqueda auxiliar por documento/nombre presente en el código |

Se revisaron `app.py`, configuración, servicios, plantillas, JavaScript y archivos
de datos locales. El Excel y los JSON son catálogos geográficos: no contienen los
usuarios, saldos, recargas ni reportes de la base perdida.

**Este SQL reconstruye la estructura. No recupera datos perdidos.** La base nueva
queda vacía. Si aparece un respaldo, conserva sus UUID, IDs, hashes de contraseña,
saldos y fechas; no vuelvas a registrar a las personas con nuevos IDs para luego
importar sus movimientos antiguos. Un hash de contraseña no se reemplaza por
contraseña en texto ni por un hash de otro algoritmo.

## Conectar la aplicación

1. Ejecuta `schema.sql` en el proyecto correcto. Si hay un error, detente y revisa
   el mensaje: el bloque transaccional evita dejar la reconstrucción a medias.
2. En el `.env` del servidor configura las variables que **ya leen** `app.py` y
   `config.py`:

   ```dotenv
   SUPABASE_URL=https://TU-PROYECTO.supabase.co
   SUPABASE_KEY=TU_CLAVE_SERVICE_ROLE_DEL_MISMO_PROYECTO
   SECRET_KEY=UN_SECRETO_ALEATORIO_LARGO_Y_PRIVADO
   ```

   El `.env` revisado utiliza una clave `sb_publishable_...`. Debes reemplazarla
   por la clave **legacy `service_role` (JWT)** para este backend y sus dependencias
   fijadas (`supabase==2.5.1`). No basta agregar `SUPABASE_SERVICE_ROLE_KEY`: el
   código actual solo lee `SUPABASE_KEY`. No se ha modificado tu `.env`.

   La aplicación autentica con sesiones Flask y `public.users`; no usa Supabase
   Auth. El SQL activa RLS y restringe las tablas al backend. No desactives RLS
   ni abras políticas públicas para hacer funcionar una clave pública. Mantén la
   clave `service_role` exclusivamente en el servidor, fuera de HTML/JavaScript.
   Referencias oficiales: [claves API](https://supabase.com/docs/guides/getting-started/api-keys)
   y [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).
3. Reinicia Flask con las dependencias de `requirements.txt` instaladas.
4. Ejecuta `verificar_base_datos.sql` en Supabase. Solo consulta estructura y
   conteos; no muestra contraseñas ni modifica registros.
5. Prueba registro, pantalla de pago pendiente, aprobación, inicio de sesión,
   perfil, creación de reporte, mapa y consulta con descuento de saldo. `/health`
   por sí solo no comprueba la conexión: responde sin consultar la base.

## Primer administrador, si no existe respaldo de usuarios

Registra tu propia cuenta desde `/register` para que Flask genere el hash correcto.
Después, en el SQL Editor, sustituye el correo de este ejemplo por el tuyo y ejecuta
este bloque una sola vez. Solo activa esa cuenta y le asigna el rol administrativo;
no inventa pagos ni carga saldo. La recarga inicial queda pendiente hasta que se
procese un pago real.

```sql
begin;
do $$
declare
    owner_email text := 'CAMBIA_POR_TU_CORREO';
    affected integer;
begin
    if owner_email = 'CAMBIA_POR_TU_CORREO' then
        raise exception 'Primero sustituye el correo del administrador';
    end if;
    update public.users
    set rol = 'admin', activo = true, is_active = true,
        estado_cuenta = 'activo', updated_at = now()
    where email = lower(trim(owner_email));
    get diagnostics affected = row_count;
    if affected <> 1 then
        raise exception 'Debe existir exactamente una cuenta con ese correo';
    end if;
end $$;
commit;
```

Cierra sesión y vuelve a entrar después de cambiar el rol: Flask lo guarda en la
sesión al iniciar sesión.

## Compatibilidad y conservación

- `users.id` y las referencias a usuarios son UUID. `recargas.id` es un entero
  autogenerado porque las rutas Flask usan `<int:recarga_id>`.
- `target_document` permite `NULL`: el formulario actual siempre lo envía así.
  No se inventan documentos para satisfacer la restricción antigua.
- Teléfonos y documentos son texto, para conservar prefijos y ceros iniciales.
- Los importes son `numeric(12,2)`; el código actual convierte el saldo a entero
  al actualizarlo. El SQL no cambia esa lógica ni redondea registros existentes.
- `saldo` es el valor prioritario en la aplicación. Al migrar el esquema antiguo,
  se copia `balance` únicamente si la columna `saldo` aún no existe. Una segunda
  ejecución no sobrescribe ninguno de los dos valores, aunque sean diferentes.
- Para el esquema antiguo, `activo` se deriva de `is_active` y `estado_cuenta` de
  `activo` únicamente si las columnas faltaban. El SQL no activa cuentas nuevas.
- `is_active` se conserva por compatibilidad histórica; el login actual consulta
  `activo` y `estado_cuenta`. No se agregan triggers que alteren los saldos o que
  dupliquen los abonos que ya hace Python.
- No hay datos demo en el script nuevo. Las consultas actuales buscan en
  `negative_reports`; cargar solamente `people_records` no restaura los reportes.
- Las fechas son `timestamptz`. La aplicación hace la conversión del mapa a
  `America/Bogota`.
- Se admite una base vacía, la reconstruida por este archivo y el esquema antiguo
  conservado en `tests/fixtures/schema_anterior.sql`. **Ese archivo de pruebas no
  se ejecuta en producción**. Un esquema distinto requiere comparar tipos,
  restricciones, permisos y triggers antes de usarlo.
- No hay `DROP TABLE`, `TRUNCATE`, eliminación de filas ni sustitución de IDs.
  Sí se actualizan permisos: `anon` y `authenticated` dejan de tener acceso directo
  a estas seis tablas. Otros clientes que dependieran de ese acceso deben revisarse.

Si luego importas un respaldo, restaura primero `users` y luego las tablas que
referencian sus IDs. Tras importar IDs explícitos de recargas, ajusta su secuencia
antes de permitir nuevas escrituras (esto no es necesario con una base vacía):

```sql
-- Aplicación detenida, después de importar; no reduce una secuencia adelantada.
do $$
declare
    seq_name text := pg_get_serial_sequence('public.recargas', 'id');
    seq_last bigint;
    max_id bigint;
begin
    select max(id) into max_id from public.recargas;
    if max_id is not null then
        execute format('select last_value from %s', seq_name) into seq_last;
        perform setval(seq_name::regclass, greatest(seq_last, max_id), true);
    end if;
end $$;
```

## Límites detectados en el código actual

El SQL no corrige estos comportamientos de `app.py`, que deben tenerse en cuenta
antes de volver a exponer la aplicación en producción:

- Las tres rutas administrativas de recargas no tienen aplicado el decorador
  `@admin_required`, aunque la función existe. RLS no compensa esto cuando Flask
  usa la clave del servidor.
- `/saldo/recarga-demo` abona saldo sin un pago real a un usuario que haya iniciado
  sesión. Wompi y notificaciones siguen siendo funciones de demostración.
- La aprobación y el cobro hacen varias peticiones independientes. Un fallo parcial
  o solicitudes simultáneas pueden dejar movimientos y saldos inconsistentes.
- Rechazar cualquier recarga desactiva al usuario, incluso si ya tenía cuenta activa.
- La recarga de billetera usa un número WhatsApp de ejemplo en `app.py`.

Estos son hallazgos del código, no errores que se resuelvan recreando tablas.
No se ha modificado `app.py` ni ejecutado escrituras contra tu Supabase.

## Validación realizada

El 4 de noviembre de 2026 se ejecutó `tests/test_schema.py` contra PostgreSQL 18.4
en una instancia local temporal, sin cargar `.env` ni usar bases existentes.
Pasaron las siguientes comprobaciones:

- Correspondencia de las seis tablas y 49 columnas usadas explícitamente en
  consultas, filtros y payloads de `app.py` con las columnas reales creadas.
- Creación vacía, payloads SQL de registro, recargas, aprobación, reporte sin
  documento, consulta con débito, rechazo, claves foráneas y unicidad de correo.
- Segunda ejecución con datos en las seis tablas, sin cambiar esos registros.
- Migración del esquema anterior conservando IDs, hashes, saldos con decimales,
  usuarios activos/inactivos, reportes e historiales; sin corregir automáticamente
  diferencias preexistentes entre `saldo` y `balance`.
- Acceso del rol backend, bloqueo de acceso directo para `anon`/`authenticated`
  y ejecución de `verificar_base_datos.sql`.
- Reversión completa ante una tabla de recargas incompatible sin secuencia de ID.

Estas pruebas verifican PostgreSQL y el contrato de datos del código. No son una
prueba HTTP de Flask/PostgREST ni de tu nuevo proyecto Supabase; esa comprobación
requiere ejecutar el script allí, configurar la clave y probar los flujos indicados.

Para repetir las pruebas en Windows con PostgreSQL instalado:

```powershell
python tests/test_schema.py --pg-bin "C:/Program Files/PostgreSQL/18/bin"
```
