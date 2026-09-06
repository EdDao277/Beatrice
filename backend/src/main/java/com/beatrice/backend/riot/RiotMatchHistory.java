package com.beatrice.backend.riot;

import java.time.Instant;
import java.util.*;
import java.util.function.*;
import tools.jackson.databind.JsonNode;

/** Scan one chronological history, rather than concatenating 100 games from each queue. */
public final class RiotMatchHistory {
    private RiotMatchHistory() {}
    public static final int TARGET = 100;
    private static final int SCAN_LIMIT = 300;
    public record Result(List<JsonNode> matches,int scanned,boolean limited) {}
    public static Result collect(String puuid, Function<String,JsonNode> fetch, BiConsumer<Integer,Integer> progress) {
        var selected = new ArrayList<JsonNode>();
        var seen = new HashSet<String>();
        int scanned = 0;
        // Fix the upper bound so newly completed games cannot shift pagination during this refresh.
        long endTime = Instant.now().getEpochSecond();
        for (int start=0; start<SCAN_LIMIT; start+=100) {
            var ids = fetch.apply("/lol/match/v5/matches/by-puuid/"+RiotClient.segment(puuid)
                +"/ids?start="+start+"&count=100&endTime="+endTime);
            if (!ids.isArray()) throw new IllegalStateException("Invalid match list");
            for (var id : ids) {
                if (!seen.add(id.asString())) continue;
                var match = fetch.apply("/lol/match/v5/matches/"+RiotClient.segment(id.asString()));
                scanned++;
                if (RiotStats.eligiblePlayer(puuid,match) != null) selected.add(match);
                progress.accept(scanned,selected.size());
                if (selected.size()==TARGET) return new Result(List.copyOf(selected),scanned,false);
            }
            if (ids.size()<100) return new Result(List.copyOf(selected),scanned,false);
        }
        return new Result(List.copyOf(selected),scanned,true);
    }
}
