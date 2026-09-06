-- Immutable snapshots preserve what was recorded even after a roster is edited.
create table recorded_games (
    id bigint generated always as identity primary key,
    team_id bigint not null references teams(id),
    request_id uuid not null unique,
    format text not null check (format in ('RANKED', 'TOURNAMENT')),
    side text not null check (side in ('BLUE', 'RED')),
    result text not null check (result in ('WIN', 'LOSS')),
    patch text not null,
    actions jsonb not null check (jsonb_typeof(actions) = 'array' and jsonb_array_length(actions) = 20),
    roster jsonb not null check (jsonb_typeof(roster) = 'object'),
    champion_names jsonb not null check (jsonb_typeof(champion_names) = 'object'),
    request_payload jsonb not null,
    recorded_at timestamptz not null default current_timestamp
);
create index recorded_games_team_date on recorded_games(team_id, recorded_at desc, id desc);
