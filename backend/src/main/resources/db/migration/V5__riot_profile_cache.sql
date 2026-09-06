-- Riot snapshots are not roster edits, manual game results, or CompCraft reference evidence.
create table riot_profile_cache (
    riot_id text primary key,
    snapshot jsonb not null
);
