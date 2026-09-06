-- External per-player evidence only. These rows never become manually recorded team games.
create table riot_match_evidence (
    puuid text not null,
    match_id text not null,
    started_at bigint not null,
    evidence jsonb not null,
    primary key (puuid, match_id)
);
create index riot_match_evidence_period on riot_match_evidence (puuid, started_at);
create table riot_split_cursor (
    puuid text not null,
    split_start bigint not null,
    through_time bigint not null,
    primary key (puuid, split_start)
);
