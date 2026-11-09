-- Solo lectura. Ejecutar DESPUÉS de schema.sql como postgres en Supabase.
-- Deben aparecer las seis tablas; en una reconstrucción vacía los conteos son 0.
select 'users' as tabla, count(*) as registros from public.users
union all select 'recargas', count(*) from public.recargas
union all select 'balance_transactions', count(*) from public.balance_transactions
union all select 'people_records', count(*) from public.people_records
union all select 'query_history', count(*) from public.query_history
union all select 'negative_reports', count(*) from public.negative_reports;

select table_name, column_name, data_type, is_nullable, column_default, is_identity
from information_schema.columns
where table_schema = 'public'
  and table_name in ('users', 'recargas', 'balance_transactions',
                    'people_records', 'query_history', 'negative_reports')
order by table_name, ordinal_position;

-- rls y acceso_backend deben ser true; acceso_publico debe ser false.
select c.relname as tabla, c.relrowsecurity as rls,
       has_table_privilege('service_role', c.oid, 'SELECT')
       and has_table_privilege('service_role', c.oid, 'INSERT')
       and has_table_privilege('service_role', c.oid, 'UPDATE')
       and has_table_privilege('service_role', c.oid, 'DELETE') as acceso_backend,
       has_table_privilege('anon', c.oid, 'SELECT')
       or has_table_privilege('authenticated', c.oid, 'SELECT') as acceso_publico
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public'
  and c.relname in ('users', 'recargas', 'balance_transactions',
                   'people_records', 'query_history', 'negative_reports');

select pg_get_serial_sequence('public.recargas', 'id') as secuencia_recargas;

-- Diagnóstico: no corrige diferencias, saldos ni estados automáticamente.
select count(*) as usuarios_con_saldos_distintos
from public.users where saldo is distinct from balance;

select count(*) as reportes_activos_sin_ubicacion_completa
from public.negative_reports
where status = 'activo'
  and (nullif(trim(city), '') is null or nullif(trim(department), '') is null
       or lat is null or lng is null);
