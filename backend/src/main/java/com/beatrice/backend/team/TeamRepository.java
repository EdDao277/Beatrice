package com.beatrice.backend.team;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import static com.beatrice.backend.team.TeamData.*;

/** Parameterized SQL keeps user input out of SQL syntax. */
@Repository
public class TeamRepository {
    private final JdbcTemplate jdbc;
    public TeamRepository(JdbcTemplate jdbc) { this.jdbc = jdbc; }

    public List<Long> ids() {
        return jdbc.queryForList("select id from teams order by lower(name), id", Long.class);
    }
    public Team find(long id) {
        var rows = jdbc.query("select id, name, version from teams where id = ?",
            (rs, row) -> new Team(rs.getLong("id"), rs.getString("name"), rs.getLong("version"), List.of()), id);
        if (rows.isEmpty()) return null;
        var head = rows.getFirst();
        var players = java.util.Arrays.stream(Role.values()).map(role -> {
            var pool = jdbc.query("select champion, comfort from champion_pools where team_id=? and role=? order by lower(champion)",
                (rs, row) -> new Champion(rs.getString("champion"), rs.getInt("comfort")), id, role.name());
            return jdbc.queryForObject("select name, riot_id from roster_slots where team_id=? and role=?",
                (rs, row) -> new Player(role, rs.getString("name"), rs.getString("riot_id"), pool), id, role.name());
        }).toList();
        return new Team(id, head.name(), head.version(), players);
    }
    public long create(String name) {
        long id = jdbc.queryForObject("insert into teams(name) values (?) returning id", Long.class, name);
        for (var role : Role.values()) {
            jdbc.update("insert into roster_slots(team_id, role) values (?, ?)", id, role.name());
        }
        return id;
    }
    public boolean update(long id, Update request) {
        // Optimistic concurrency: stale clients must reload before overwriting a roster.
        int changed = jdbc.update("update teams set name=?, version=version+1, updated_at=current_timestamp where id=? and version=?",
            request.name(), id, request.version());
        if (changed == 0) return false;
        for (var player : request.players()) {
            jdbc.update("update roster_slots set name=?, riot_id=? where team_id=? and role=?",
                player.name(), player.riotId(), id, player.role().name());
            jdbc.update("delete from champion_pools where team_id=? and role=?", id, player.role().name());
            for (var champion : player.champions()) {
                jdbc.update("insert into champion_pools(team_id, role, champion, comfort) values (?, ?, ?, ?)",
                    id, player.role().name(), champion.name(), champion.comfort());
            }
        }
        return true;
    }
}

