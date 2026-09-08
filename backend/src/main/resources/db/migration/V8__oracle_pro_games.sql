-- Oracle evidence is isolated from collected matches, champion metadata and saved team games.
create table oracle_imports (
    id bigint generated always as identity primary key,
    sha256 text not null unique,
    imported_at timestamptz not null default now(),
    report jsonb not null
);
create table oracle_matches (
    game_id text primary key,
    played_at timestamp not null,
    patch text not null,
    league text not null,
    draft_fields_complete boolean not null,
    sha256 text not null,
    payload jsonb not null
);
create index oracle_matches_patch_date_idx on oracle_matches(patch, played_at);
create table oracle_match_sources (
    import_id bigint not null references oracle_imports(id),
    game_id text not null references oracle_matches(game_id),
    source_hashes jsonb not null,
    primary key(import_id, game_id)
);
create index oracle_match_sources_game_idx on oracle_match_sources(game_id);
