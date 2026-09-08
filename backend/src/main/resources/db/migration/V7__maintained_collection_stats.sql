-- Additive only: archived metadata/stats and manually recorded games are untouched.
create table collection_datasets (
    id text primary key,
    split_start bigint not null,
    metadata_import_id bigint not null references reference_imports(id)
);
create table collection_players (
    dataset_id text not null references collection_datasets(id),
    puuid text not null,
    depth integer not null,
    primary key(dataset_id,puuid)
);
create table collection_cursors (
    dataset_id text not null,
    puuid text not null,
    queue_id integer not null,
    window_start bigint not null,
    window_end bigint not null,
    position integer not null default 0,
    done boolean not null default false,
    primary key(dataset_id,puuid,queue_id),
    foreign key(dataset_id,puuid) references collection_players(dataset_id,puuid)
);
create table collection_matches (
    dataset_id text not null references collection_datasets(id),
    match_id text not null,
    accepted boolean not null,
    participant_puuids jsonb not null default '[]',
    primary key(dataset_id,match_id)
);
create table collection_runs (
    id bigint generated always as identity primary key,
    dataset_id text not null references collection_datasets(id),
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    status text not null default 'RUNNING',
    downloaded integer not null default 0,
    accepted integer not null default 0
);
-- Common dimensions permit exact, source-separated counts. Empty partner/signature
-- dimensions are intentional, never SQL NULL, so uniqueness also covers role rows.
create table champion_role_stats (
    dataset_id text not null references collection_datasets(id),
    patch text not null,
    queue_id integer not null,
    champion_id text not null default '',
    role text not null default '',
    partner_id text not null default '',
    partner_role text not null default '',
    signature text not null default '',
    games bigint not null check(games>0),
    wins bigint not null check(wins>=0 and wins<=games),
    win_rate double precision generated always as (wins::double precision/games) stored,
    low_sample boolean generated always as (games<30) stored,
    primary key(dataset_id,patch,queue_id,champion_id,role,partner_id,partner_role,signature)
);
create table champion_synergy_stats (like champion_role_stats including all);
alter table champion_synergy_stats add foreign key(dataset_id) references collection_datasets(id);
create table champion_matchup_stats (like champion_role_stats including all);
alter table champion_matchup_stats add foreign key(dataset_id) references collection_datasets(id);
create table team_comp_signature_stats (like champion_role_stats including all);
alter table team_comp_signature_stats add foreign key(dataset_id) references collection_datasets(id);
