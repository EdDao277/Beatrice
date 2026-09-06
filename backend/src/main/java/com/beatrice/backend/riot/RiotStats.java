package com.beatrice.backend.riot;

import java.util.*;
import tools.jackson.databind.JsonNode;

/** Recent match evidence is deliberately separate from the ranked season record. */
public final class RiotStats {
    private RiotStats() {}
    public record Champion(String id, String name, int games, int wins, double winRate) {}
    public record Sample(int games, List<Champion> champions) {}
    public static Sample summarize(String puuid, List<JsonNode> matches) {
        var counts = new HashMap<String,int[]>();
        int games = 0;
        for (var match : matches) {
            var info = match.path("info");
            if (info.path("queueId").asInt() != 420) continue;
            for (var player : info.path("participants")) {
                if (!puuid.equals(player.path("puuid").asString())) continue;
                if (player.path("gameEndedInEarlySurrender").asBoolean(false)) break;
                String champion = player.path("championName").asString();
                if (champion.isBlank()) break;
                if (champion.equals("FiddleSticks")) champion = "Fiddlesticks";
                if (champion.equals("Wukong")) champion = "MonkeyKing";
                var count = counts.computeIfAbsent(champion, unused -> new int[2]);
                count[0]++; if (player.path("win").asBoolean()) count[1]++;
                games++; break;
            }
        }
        var champions = counts.entrySet().stream().map(e -> new Champion(e.getKey(), e.getKey(), e.getValue()[0], e.getValue()[1],
            100.0 * e.getValue()[1] / e.getValue()[0]))
            .sorted(Comparator.comparingInt(Champion::games).reversed().thenComparing(Champion::id)).limit(3).toList();
        return new Sample(games, champions);
    }
}
