-- DB schema. Same as supabase/migrations/20261015095433_init_schema.sql and backend/app/database/models.py

create type zone_type as enum ('FACTORY', 'OFFICE');
create type camera_type as enum ('DAHUA', 'HIKVISION', 'GENERIC_RTSP', 'LOCAL_WEBCAM', 'BROWSER');
create type camera_status as enum ('OFFLINE', 'CONNECTING', 'ONLINE', 'STREAMING', 'ERROR', 'RECONNECTING');
create type violation_type as enum ('NO_HELMET', 'NO_WORK_UNIFORM', 'OTHER_SAFETY_VIOLATION');
create type violation_status as enum ('OPEN', 'ACKNOWLEDGED', 'RESOLVED');
create type user_role as enum ('ADMIN', 'HUB_EMPLOYEE');

create table zones (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    type zone_type not null,
    description text,
    created_at timestamptz not null default now()
);

create table cameras (
    id uuid primary key default gen_random_uuid(),
    name text not null unique,
    ip_address text not null,
    rtsp_port integer not null default 554,
    username text not null,
    password_encrypted text,
    camera_type camera_type not null default 'DAHUA',
    channel integer not null default 1,
    subtype integer not null default 0,
    zone_id uuid references zones(id) on delete set null,
    status camera_status not null default 'OFFLINE',
    mirror boolean not null default false,
    rotation integer not null default 0 check (rotation in (0, 90, 180, 270)),
    ai_enabled boolean not null default true,
    enabled boolean not null default true,
    last_connected_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table violations (
    id uuid primary key default gen_random_uuid(),
    camera_id uuid not null references cameras(id) on delete cascade,
    zone_id uuid references zones(id) on delete set null,
    violation_type violation_type not null,
    person_id text,
    confidence double precision,
    snapshot_url text,
    storage_path text,
    detected_at timestamptz not null default now(),
    status violation_status not null default 'OPEN',
    resolved_at timestamptz,
    resolved_by text,
    created_at timestamptz not null default now()
);
create index violations_detected_at_idx on violations (detected_at desc);
create index violations_camera_id_idx on violations (camera_id);
create index violations_status_idx on violations (status);

create table users (
    id uuid primary key default gen_random_uuid(),
    email varchar not null unique,
    full_name text,
    password_hash text not null,
    role user_role not null default 'HUB_EMPLOYEE',
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    last_login_at timestamptz
);

create table app_settings (
    key text primary key,
    value jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

-- Only the backend (service role) uses these tables, never the browser
alter table zones enable row level security;
alter table cameras enable row level security;
alter table violations enable row level security;
alter table users enable row level security;
alter table app_settings enable row level security;

-- Private bucket for violation photos (backend gives signed URLs)
insert into storage.buckets (id, name, public)
values ('violation-snapshots', 'violation-snapshots', false)
on conflict (id) do nothing;
