package com.beatrice.backend.riot;

import java.util.*;
import tools.jackson.databind.JsonNode;

/** Recent match evidence is deliberately separate from the ranked season record. */
public final class RiotStats {
    private RiotStats() {}
    public static final List<Integer> QUEUES = List.of(400,420,440,710);
    public record Champion(String id, String name, int games, int wins, double winRate) {}
    public record Sample(int games, List<Champion> champions, Map<String,Integer> modeGames) {
        // Sum game counts, never average champion percentages (unequal denominators).
        public int wins() { return champions.stream().mapToInt(Champion::wins).sum(); }
    }
    static JsonNode eligiblePlayer(String puuid, JsonNode match) {
        var info = match.path("info");
        if (!QUEUES.contains(info.path("queueId").asInt())) return null;
        for (var player : info.path("participants")) if (puuid.equals(player.path("puuid").asString())) {
            return player.path("gameEndedInEarlySurrender").asBoolean(false) || player.path("championName").asString().isBlank() ? null : player;
        }
        return null;
    }
    public static Sample summarize(String puuid, List<JsonNode> matches) {
        var counts = new HashMap<String,int[]>();
        var modeGames = new TreeMap<String,Integer>();
        int games = 0;
        for (var match : matches) {
            var player = eligiblePlayer(puuid,match);
            if (player != null) {
                String champion = player.path("championName").asString();
                if (champion.equals("FiddleSticks")) champion = "Fiddlesticks";
                if (champion.equals("Wukong")) champion = "MonkeyKing";
                var count = counts.computeIfAbsent(champion, unused -> new int[2]);
                count[0]++; if (player.path("win").asBoolean()) count[1]++;
                games++;
                modeGames.merge(String.valueOf(match.path("info").path("queueId").asInt()),1,Integer::sum);
            }
        }
        var champions = counts.entrySet().stream().map(e -> new Champion(e.getKey(), e.getKey(), e.getValue()[0], e.getValue()[1],
            100.0 * e.getValue()[1] / e.getValue()[0]))
            .sorted(Comparator.comparingInt(Champion::games).reversed().thenComparing(Champion::id)).toList();
        return new Sample(games, champions, modeGames);
    }
}
