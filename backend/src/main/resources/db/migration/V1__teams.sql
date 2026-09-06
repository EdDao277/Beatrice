-- Flyway applies this once. Future schema changes belong in new migrations.
create table teams (
 id bigint generated always as identity primary key,
 name text not null check (length(btrim(name)) between 1 and 80),
 version bigint not null default 0,
 created_at timestamptz not null default current_timestamp,
 updated_at timestamptz not null default current_timestamp
);
create unique index teams_name_unique on teams (lower(btrim(name)));
-- A composite key permits at most one player in each of the five fixed slots.
create table roster_slots (
 team_id bigint not null references teams(id) on delete cascade,
 role text not null check (role in ('TOP','JUNGLE','MID','BOT','SUPPORT')),
 name text not null default '',
 riot_id text not null default '',
 primary key (team_id, role)
);
create table champion_pools (
 team_id bigint not null,
 role text not null,
 champion text not null check (length(btrim(champion)) between 1 and 50),
 comfort integer not null check (comfort between 1 and 5),
 foreign key (team_id, role) references roster_slots(team_id, role) on delete cascade
);
create unique index champion_pool_unique on champion_pools(team_id, role, lower(champion));

