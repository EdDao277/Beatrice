package com.beatrice.backend.collection;

import java.time.Instant;
import java.util.List;

public record CollectionConfig(String platform,String region,List<String> seedRiotIds,List<Integer> queues,
    int maxNewMatchesPerRun,int maxDiscoveryDepth,int maxTrackedPlayers,String splitStart) {
    public long start() { return Instant.parse(splitStart==null ? "2026-07-29T19:00:00Z" : splitStart).getEpochSecond(); }
    public void validate() {
        if (!"na1".equals(platform) || !"americas".equals(region)) throw new IllegalArgumentException("Only NA1/Americas is supported.");
        if (seedRiotIds==null || seedRiotIds.isEmpty() || seedRiotIds.size()>100 || seedRiotIds.stream().anyMatch(s->s==null || !s.matches("[^#]+#[^#]+"))) throw new IllegalArgumentException("Provide 1–100 full seed Riot IDs.");
        if (queues==null || queues.isEmpty() || queues.size()!=queues.stream().distinct().count() || !List.of(400,420,440,710).containsAll(queues)) throw new IllegalArgumentException("Use unique supported queue IDs: 400,420,440,710.");
        if(maxNewMatchesPerRun<1 || maxNewMatchesPerRun>1000 || maxDiscoveryDepth<0 || maxDiscoveryDepth>2 || maxTrackedPlayers<seedRiotIds.size() || maxTrackedPlayers>1000) throw new IllegalArgumentException("Invalid collection limits.");
        if(start()>=Instant.now().getEpochSecond()) throw new IllegalArgumentException("Split start must be in the past.");
    }
}
