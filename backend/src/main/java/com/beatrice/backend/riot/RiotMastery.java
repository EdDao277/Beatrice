package com.beatrice.backend.riot;

import java.util.*;
import java.util.function.LongFunction;
import tools.jackson.databind.JsonNode;

public final class RiotMastery {
    private RiotMastery() {}
    public record Champion(String id,int level,long points) {}
    public static List<Champion> top(JsonNode entries,LongFunction<String> resolve) {
        if (!entries.isArray()) throw new IllegalStateException("Invalid mastery response");
        var champions = new ArrayList<Champion>();
        for (var entry : entries) champions.add(new Champion(resolve.apply(entry.path("championId").asLong()),
            entry.path("championLevel").asInt(),entry.path("championPoints").asLong()));
        return champions.stream().sorted(Comparator.comparingLong(Champion::points).reversed().thenComparing(Champion::id)).limit(3).toList();
    }
}
