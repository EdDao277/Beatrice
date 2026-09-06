-- Preserve the meaning of existing ratings: 3/5 becomes 6/10.
-- Reject stale forms that still contain old-scale values after restart.
update teams set version = version + 1, updated_at = current_timestamp
where id in (select team_id from champion_pools);

alter table champion_pools drop constraint champion_pools_comfort_check;
update champion_pools set comfort = comfort * 2;
alter table champion_pools add constraint champion_pools_comfort_check
    check (comfort between 1 and 10);
