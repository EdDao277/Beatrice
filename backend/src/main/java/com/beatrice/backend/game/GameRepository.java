package com.beatrice.backend.game;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import tools.jackson.databind.ObjectMapper;
import com.beatrice.backend.team.TeamData.Team;
import static com.beatrice.backend.game.GameData.*;

@Repository
public class GameRepository {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    public GameRepository(JdbcTemplate jdbc, ObjectMapper mapper) { this.jdbc=jdbc; this.mapper=mapper; }
    public void lockTeamSnapshot(long teamId) {
        // Roster edits lock this same parent row first. Hold a shared lock until the
        // game commits so the snapshot cannot mix old slots with a newer pool.
        jdbc.queryForList("select id from teams where id=? for share", Long.class, teamId);
    }
    public List<Game> list(long teamId) {
        return jdbc.query("select * from recorded_games where team_id=? order by recorded_at desc, id desc", (rs,n) ->
            new Game(rs.getLong("id"), rs.getLong("team_id"), Format.valueOf(rs.getString("format")),
                Side.valueOf(rs.getString("side")), Result.valueOf(rs.getString("result")), rs.getString("patch"),
                Arrays.asList(mapper.readValue(rs.getString("actions"), Action[].class)),
                mapper.readValue(rs.getString("roster"), Team.class),
                mapper.readValue(rs.getString("champion_names"), new tools.jackson.core.type.TypeReference<Map<String,String>>() {}),
                rs.getTimestamp("recorded_at").toInstant(),
                Arrays.asList(mapper.readValue(rs.getString("assignments"), Assignment[].class)),
                rs.getLong("assignment_version")), teamId);
    }
    public boolean updateAssignments(long teamId, long id, AssignmentUpdate request) {
        // Optimistic locking prevents another tab's lineup from being silently overwritten.
        return jdbc.update("update recorded_games set assignments=?::jsonb, assignment_version=assignment_version+1 where team_id=? and id=? and assignment_version=?",
            mapper.writeValueAsString(request.assignments()), teamId, id, request.version()) == 1;
    }
    public Long existingId(UUID requestId) {
        var ids=jdbc.queryForList("select id from recorded_games where request_id=?", Long.class, requestId);
        return ids.isEmpty() ? null : ids.getFirst();
    }
    public boolean sameRequest(long teamId, Create request) {
        return Boolean.TRUE.equals(jdbc.queryForObject("select exists(select 1 from recorded_games where request_id=? and team_id=? and request_payload=?::jsonb)",
            Boolean.class, request.requestId(), teamId, mapper.writeValueAsString(request)));
    }
    public void insert(long teamId, Create request, Team roster, Map<String, String> championNames) {
        jdbc.update("""
            insert into recorded_games(team_id,request_id,format,side,result,patch,actions,roster,champion_names,request_payload)
            values (?,?,?,?,?,?,?::jsonb,?::jsonb,?::jsonb,?::jsonb) on conflict (request_id) do nothing
            """, teamId, request.requestId(), request.format().name(), request.side().name(), request.result().name(), request.patch(),
            mapper.writeValueAsString(request.actions()), mapper.writeValueAsString(roster), mapper.writeValueAsString(championNames), mapper.writeValueAsString(request));
    }
}
