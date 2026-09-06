package com.beatrice.backend.riot;

import java.time.Instant;
import java.util.*;
import java.util.function.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import tools.jackson.databind.*;

/** Persistent match details make failed/capped syncs retryable without downloading them again. */
@Service
public class RiotSplitHistory {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    public record Result(RiotStats.Sample sample, boolean complete) {}
    public RiotSplitHistory(JdbcTemplate jdbc,ObjectMapper mapper) { this.jdbc=jdbc; this.mapper=mapper; }
    public Result sync(String puuid,Instant start,Instant end,Function<String,JsonNode> fetch,IntConsumer progress) {
        long lower = start.getEpochSecond(), upper = end.getEpochSecond();
        var cursors = jdbc.queryForList("select through_time from riot_split_cursor where puuid=? and split_start=?",Long.class,puuid,lower);
        // Recheck the last day for delayed match availability; cached IDs remain idempotent.
        long fetchFrom = cursors.isEmpty() ? lower : Math.max(lower,cursors.getFirst()-86400);
        var seen = new HashSet<String>();
        int downloaded = 0;
        boolean complete = false;
        scan: for (int offset=0; offset<100000; offset+=100) {
            var ids = fetch.apply("/lol/match/v5/matches/by-puuid/"+RiotClient.segment(puuid)
                +"/ids?start="+offset+"&count=100&startTime="+fetchFrom+"&endTime="+upper);
            if (!ids.isArray()) throw new IllegalStateException("Invalid match list");
            for (var idNode : ids) {
                String id = idNode.asString();
                if (id.isBlank()) throw new IllegalStateException("Invalid match ID");
                if (!seen.add(id)) continue;
                if (jdbc.queryForObject("select count(*) from riot_match_evidence where puuid=? and match_id=?",Integer.class,puuid,id)>0) continue;
                // Bound a job so one busy account cannot monopolize all five roster refreshes.
                if (downloaded>=300) break scan;
                var match = fetch.apply("/lol/match/v5/matches/"+RiotClient.segment(id));
                var info = match.path("info");
                long timestamp = info.path("gameStartTimestamp").asLong(0)/1000;
                JsonNode participant = null;
                for (var player : info.path("participants")) if (puuid.equals(player.path("puuid").asString())) participant=player;
                if (timestamp<=0 || participant==null) throw new IllegalStateException("Invalid match evidence");
                // Retain only fields needed for this player's stats, not everyone else's payload.
                var evidence = mapper.createObjectNode();
                var compact = evidence.putObject("info");
                compact.put("queueId",info.path("queueId").asInt());
                var player = compact.putArray("participants").addObject();
                player.put("puuid",puuid);
                player.put("championName",participant.path("championName").asString());
                player.put("win",participant.path("win").asBoolean());
                player.put("gameEndedInEarlySurrender",participant.path("gameEndedInEarlySurrender").asBoolean(false));
                jdbc.update("insert into riot_match_evidence(puuid,match_id,started_at,evidence) values (?,?,?,?::jsonb) on conflict do nothing",
                    puuid,id,timestamp,mapper.writeValueAsString(evidence));
                progress.accept(++downloaded);
            }
            if (ids.size()<100) { complete=true; break; }
        }
        // Advance only after exhausting the window. Failure/caps leave the old cursor intact.
        if (complete) jdbc.update("insert into riot_split_cursor(puuid,split_start,through_time) values (?,?,?) on conflict(puuid,split_start) do update set through_time=excluded.through_time",puuid,lower,upper);
        var matches = jdbc.queryForList("select evidence::text from riot_match_evidence where puuid=? and started_at>=? and started_at<?",String.class,puuid,lower,upper)
            .stream().map(mapper::readTree).toList();
        return new Result(RiotStats.summarize(puuid,matches),complete);
    }
}
