-- Imported evidence is append-only and deliberately separate from local team history.
create table reference_imports (
    id bigint generated always as identity primary key,
    sha256 text not null unique,
    filename text not null,
    imported_at timestamptz not null default current_timestamp,
    report jsonb not null default '{}'
);
create table reference_champion_metadata (
    import_id bigint not null references reference_imports(id),
    champion_id text not null,
    roles jsonb not null,
    raw_metadata jsonb not null,
    primary key (import_id, champion_id)
);
create table reference_stats (
    id bigint generated always as identity primary key,
    import_id bigint not null references reference_imports(id),
    kind text not null check (kind in ('ROLE','SYNERGY','MATCHUP','COMPOSITION')),
    patch text not null,
    region text not null,
    queue_id integer not null,
    source_type text not null,
    champion_id text,
    role text check (role in ('TOP','JUNGLE','MID','BOT','SUPPORT')),
    partner_id text,
    partner_role text check (partner_role in ('TOP','JUNGLE','MID','BOT','SUPPORT')),
    games integer not null check (games > 0),
    wins integer not null check (wins >= 0 and wins <= games),
    delta double precision,
    original_sample_score double precision,
    raw_stat jsonb not null
);
create index reference_stats_lookup on reference_stats(import_id,champion_id,role,patch,queue_id,region,source_type,kind);
create index reference_stats_slices on reference_stats(import_id,patch,queue_id,region,source_type);

-- Empty assignments mean unknown, never an inferred lane based on pick order.
alter table recorded_games add column assignments jsonb not null default '[]';
alter table recorded_games add column assignment_version bigint not null default 0;
