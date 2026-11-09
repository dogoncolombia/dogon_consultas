-- Ejecuta este script en el SQL Editor de Supabase
create extension if not exists pgcrypto;

create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  full_name text not null,
  email text not null unique,
  phone text,
  password_hash text not null,
  balance numeric(12,2) not null default 0,
  is_active boolean not null default true,
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists balance_transactions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  transaction_type text not null,
  amount numeric(12,2) not null,
  description text,
  reference text,
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists idx_balance_transactions_user_id on balance_transactions(user_id);

create table if not exists people_records (
  id uuid primary key default gen_random_uuid(),
  document_number text not null unique,
  full_name text not null,
  email text,
  phone text,
  city text,
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists idx_people_records_name on people_records(full_name);

create table if not exists query_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  search_term text not null,
  cost numeric(12,2) not null default 0,
  result_count integer not null default 0,
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists idx_query_history_user_id on query_history(user_id);

create table if not exists negative_reports (
  id uuid primary key default gen_random_uuid(),
  target_document text not null,
  target_name text not null,
  reason text not null,
  details text,
  status text not null default 'activo',
  created_by uuid references users(id) on delete set null,
  created_at timestamptz not null default timezone('utc', now())
);
create index if not exists idx_negative_reports_document on negative_reports(target_document);

-- Datos demo para probar consultas
insert into people_records (document_number, full_name, email, phone, city)
values
('1001001001', 'Juan David López', 'juan@example.com', '3001112233', 'Pereira'),
('1001001002', 'María Fernanda Ríos', 'maria@example.com', '3005558899', 'Dosquebradas'),
('1001001003', 'Carlos Andrés Gómez', 'carlos@example.com', '3012224455', 'Manizales')
on conflict (document_number) do nothing;
