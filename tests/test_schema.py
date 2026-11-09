"""Prueba real en PostgreSQL aislado. No carga .env ni conecta a Supabase.

Uso: python tests/test_schema.py --pg-bin "C:/Program Files/PostgreSQL/18/bin"
Requiere solo Python estándar y binarios locales de PostgreSQL >= 13.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TABLES = {"users", "recargas", "balance_transactions", "people_records",
          "query_history", "negative_reports"}


def run(command, *, input=None):
    env = dict(os.environ, PGCLIENTENCODING="UTF8")
    # En Windows el servidor puede heredar los pipes de pg_ctl y mantenerlos
    # abiertos. Un archivo temporal permite que communicate() no quede esperando.
    if Path(command[0]).stem == "pg_ctl":
        with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=output,
                                    stderr=output, env=env, timeout=90)
            output.seek(0)
            message = output.read()
        if result.returncode:
            raise RuntimeError(message)
        return message
    result = subprocess.run(command, input=input, text=True, encoding="utf-8",
                            errors="replace", capture_output=True, env=env, timeout=90)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name}: {result.stderr}\n{result.stdout}")
    return result.stdout.strip()


def check_app_contract(sql):
    """Comparar columnas reales con select/filtros/payloads del app.py actual."""
    columns = json.loads(sql("""
        select json_object_agg(table_name, cols) from (
          select table_name, json_agg(column_name) cols
          from information_schema.columns where table_schema='public'
          group by table_name
        ) x;
    """))
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8-sig"))
    used_tables = set()
    checked = set()
    # Las funciones anidadas se analizan en su propio alcance.
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.Module)):
            continue
        nodes = []

        def visit(node):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node is not scope:
                return
            nodes.append(node)
            for child in ast.iter_child_nodes(node):
                visit(child)

        visit(scope)
        assignments = {}
        for node in nodes:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assignments.setdefault(target.id, []).append(node.value)

        def table_of(node, seen=frozenset()):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "table" and node.args and isinstance(node.args[0], ast.Constant):
                    return {node.args[0].value}
                return table_of(node.func.value, seen)
            if isinstance(node, ast.Name) and node.id not in seen:
                result = set()
                for value in assignments.get(node.id, []):
                    result |= table_of(value, seen | {node.id})
                return result
            return set()

        for node in nodes:
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            tables = table_of(node)
            used_tables |= tables
            fields = set()
            if node.func.attr in {"select", "eq", "in_", "gte", "lt", "order", "ilike"}:
                if node.args and isinstance(node.args[0], ast.Constant):
                    fields |= {s.strip() for s in str(node.args[0].value).split(",") if s.strip() != "*"}
            if node.func.attr in {"insert", "update"} and node.args:
                values = [node.args[0]]
                if isinstance(node.args[0], ast.Name):
                    values = assignments.get(node.args[0].id, [])
                for value in values:
                    if isinstance(value, ast.Dict):
                        fields |= {k.value for k in value.keys if isinstance(k, ast.Constant)}
            for table in tables:
                assert table in columns, f"Falta tabla {table}"
                for field in fields:
                    assert field in columns[table], f"Falta {table}.{field}, app.py:{node.lineno}"
                    checked.add((table, field))
    assert used_tables == TABLES, used_tables
    print(f"OK: contrato de app.py: {len(used_tables)} tablas y {len(checked)} columnas usadas")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", required=True, type=Path)
    args = parser.parse_args()
    binary = lambda name: str(args.pg_bin / (name + ".exe"))
    temp_root = Path(tempfile.gettempdir()).resolve()
    work = Path(tempfile.mkdtemp(prefix="dogon-schema-test-", dir=temp_root)).resolve()
    assert work.is_relative_to(temp_root) and work != temp_root
    data = work / "data"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = str(sock.getsockname()[1])
    started = False
    try:
        run([binary("initdb"), "-D", str(data), "-U", "postgres", "-A", "trust",
             "--encoding=UTF8", "--locale=C"])
        run([binary("pg_ctl"), "-D", str(data), "-l", str(work / "postgres.log"),
             "-o", f"-h 127.0.0.1 -p {port}", "-w", "start"])
        started = True

        def sql(query, db="fresh"):
            return run([binary("psql"), "-X", "-v", "ON_ERROR_STOP=1", "-A", "-t",
                        "-h", "127.0.0.1", "-p", port, "-U", "postgres", "-d", db], input=query)

        sql("create role anon; create role authenticated; create role service_role bypassrls;", "postgres")
        sql("create database fresh; create database legacy;", "postgres")
        schema = (ROOT / "schema.sql").read_text(encoding="utf-8-sig")
        sql(schema)
        check_app_contract(sql)
        for table in sorted(TABLES):
            assert sql(f"select count(*) from public.{table};") == "0", "Datos demo inesperados"

        # Ejercitar los payloads y defaults de registro, recarga, aprobación,
        # reporte sin documento, consulta con débito y rechazo. Rol real backend.
        sql("""
        set role service_role;
        insert into public.users(id, full_name, email, phone, password_hash,
                                 rol, activo, estado_cuenta, saldo, pending_token)
        values ('11111111-1111-1111-1111-111111111111', 'Prueba', 'prueba@example.invalid',
                '03001234567', 'hash-de-prueba-no-login', 'usuario', false, 'pendiente_pago', 0, 'token-prueba');
        insert into public.recargas(user_id, valor, tipo, estado, observacion)
        values ('11111111-1111-1111-1111-111111111111', 8000, 'recarga_inicial', 'pendiente', 'Inicial');
        do $$ begin
            if not exists(select 1 from public.users where balance=0 and saldo=0 and not activo)
               or not exists(select 1 from public.recargas where id=1 and created_at is not null) then
                raise exception 'Defaults incorrectos';
            end if;
        end $$;
        update public.users set saldo=8000, balance=8000, activo=true, estado_cuenta='activo';
        update public.recargas set estado='aprobado',
            approved_by='11111111-1111-1111-1111-111111111111', approved_at=now(), observacion='Aprobada'
        where id=1;
        insert into public.balance_transactions(user_id, amount, transaction_type, description, reference)
        values ('11111111-1111-1111-1111-111111111111',8000,'recharge_approved','Recarga aprobada','recarga_1');
        insert into public.negative_reports(target_document, target_name, phone, address,
            department, city, reason, details, lat, lng, status, created_by)
        values (null, 'Persona de prueba','03001234567','Direccion de prueba','Risaralda','Pereira',
            'Motivo','Detalle',4.81,-75.69,'activo','11111111-1111-1111-1111-111111111111');
        update public.users set saldo=7600, balance=7600, updated_at=now();
        insert into public.balance_transactions(user_id, transaction_type, amount, description, reference, created_at)
        values ('11111111-1111-1111-1111-111111111111','consulta',-400,'Consulta',null,now());
        insert into public.query_history(user_id, search_term, cost, result_count, created_at)
        values ('11111111-1111-1111-1111-111111111111','Persona',400,1,now());
        insert into public.people_records(document_number, full_name, phone, city)
        values ('001234','Persona de prueba','03001234567','Pereira');
        insert into public.recargas(user_id, valor, tipo, estado, observacion)
        values ('11111111-1111-1111-1111-111111111111',5000,'recarga_manual_whatsapp','pendiente','Manual');
        update public.recargas set estado='rechazado', approved_by=null, rejected_at=now() where id=2;
        update public.users set activo=false, estado_cuenta='pendiente_pago';
        do $$ begin
            if (select sum(amount) from public.balance_transactions) <> 7600
               or (select saldo from public.users limit 1) <> 7600
               or (select count(*) from public.negative_reports where status='activo'
                     and phone ilike '%300%' and target_name ilike '%persona%') <> 1 then
                raise exception 'Flujo de saldo/reporte inconsistente';
            end if;
            begin
                insert into public.query_history(user_id, search_term)
                values ('99999999-9999-9999-9999-999999999999','huerfano');
                raise exception 'Se acepto una referencia inexistente';
            exception when foreign_key_violation then null;
            end;
            begin
                insert into public.users(full_name,email,password_hash)
                values ('Duplicado','prueba@example.invalid','hash');
                raise exception 'Se acepto un email duplicado';
            exception when unique_violation then null;
            end;
        end $$;
        reset role;
        """)
        print("OK: registro, recargas, reporte sin documento, consulta, saldo, referencias y email unico")

        def snapshot(db):
            return {t: json.loads(sql(f"select coalesce(jsonb_agg(to_jsonb(t) order by id), '[]') from public.{t} t;", db))
                    for t in sorted(TABLES)}

        before = snapshot("fresh")
        sql(schema)
        assert snapshot("fresh") == before, "Reejecucion altero registros"
        print("OK: segunda ejecucion conserva todos los registros de las seis tablas")
        for role in ("anon", "authenticated"):
            for table in sorted(TABLES):
                try:
                    sql(f"set role {role}; select * from public.{table};")
                except RuntimeError as exc:
                    assert "permission denied" in str(exc), exc
                else:
                    raise AssertionError(f"{role} obtuvo acceso a {table}")
        assert sql("select count(*) from pg_tables where schemaname='public' and rowsecurity;") == "6"
        print("OK: RLS activo, backend operativo, acceso directo anon/authenticated denegado")
        sql((ROOT / "verificar_base_datos.sql").read_text(encoding="utf-8-sig"))

        old = (ROOT / "tests/fixtures/schema_anterior.sql").read_text(encoding="utf-8-sig")
        sql(old, "legacy")
        sql("""
            insert into users(id, full_name, email, password_hash, balance, is_active)
            values ('22222222-2222-2222-2222-222222222222','Anterior','anterior@example.invalid','hash-original',12345.67,true),
                   ('33333333-3333-3333-3333-333333333333','Inactivo','inactivo@example.invalid','otro-hash',500,false);
            insert into negative_reports(target_document,target_name,reason,created_by)
            values ('00123','Anterior','Motivo','22222222-2222-2222-2222-222222222222');
            insert into balance_transactions(user_id, transaction_type, amount)
            values ('22222222-2222-2222-2222-222222222222','recarga_demo',12345.67);
            insert into query_history(user_id,search_term,cost,result_count)
            values ('22222222-2222-2222-2222-222222222222','00123',400,1);
        """, "legacy")
        original = {t: json.loads(sql(f"select coalesce(jsonb_agg(to_jsonb(t) order by id),'[]') from public.{t} t;", "legacy"))
                    for t in sorted(TABLES - {"recargas"})}
        sql(schema, "legacy")
        migrated = snapshot("legacy")
        for table, rows in original.items():
            actual = {r["id"]: r for r in migrated[table]}
            for row in rows:
                assert all(actual[row["id"]][k] == v for k, v in row.items()), table
        assert sql("select saldo=balance and activo=is_active and estado_cuenta='activo' from users where email='anterior@example.invalid';", "legacy") == "t"
        assert sql("select saldo=balance and not activo and estado_cuenta='pendiente_pago' from users where email='inactivo@example.invalid';", "legacy") == "t"
        # Discrepancias previas no se corrigen ni se ocultan silenciosamente.
        sql("update users set saldo=0 where email='anterior@example.invalid';", "legacy")
        before = snapshot("legacy")
        sql(schema, "legacy")
        assert snapshot("legacy") == before
        print("OK: migracion antigua conserva IDs, hashes, importes, actividad, reportes e historiales")

        # Error al final del script debe revertir tambien el DDL anterior.
        sql("create database rollback_test;", "postgres")
        sql("create table users(id uuid primary key, full_name text, email text, phone text, password_hash text, balance numeric not null default 0, is_active boolean not null default true, created_at timestamptz, updated_at timestamptz); create table recargas(id bigint primary key, user_id uuid, estado text, created_at timestamptz, approved_at timestamptz, approved_by uuid);", "rollback_test")
        try:
            sql(schema, "rollback_test")
        except RuntimeError as exc:
            assert "IDENTITY" in str(exc), exc
        else:
            raise AssertionError("Se acepto recargas sin generacion de ID")
        assert sql("select count(*) from information_schema.columns where table_schema='public' and table_name='users' and column_name='saldo';", "rollback_test") == "0"
        assert sql("select count(*) from pg_tables where schemaname='public' and tablename='negative_reports';", "rollback_test") == "0"
        print("OK: fallo de esquema incompatible revierte la transaccion completa")
    finally:
        if started:
            run([binary("pg_ctl"), "-D", str(data), "-m", "fast", "-w", "stop"])
        # Solo se limpia la carpeta temporal creada por ESTA prueba.
        assert work.is_relative_to(temp_root) and work.name.startswith("dogon-schema-test-")
        shutil.rmtree(work)


if __name__ == "__main__":
    main()
