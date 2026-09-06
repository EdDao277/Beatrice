package com.beatrice.backend.riot;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class RiotStatsTest {
    final ObjectMapper mapper = new ObjectMapper();
    @Test void countsSupportedModesForThisPlayerAndExcludesRemakes() {
        var matches = List.of(
            mapper.readTree("{\"info\":{\"queueId\":420,\"participants\":[{\"puuid\":\"me\",\"championName\":\"Ashe\",\"win\":true},{\"puuid\":\"other\",\"championName\":\"Swain\",\"win\":false}]}}"),
            mapper.readTree("{\"info\":{\"queueId\":420,\"participants\":[{\"puuid\":\"me\",\"championName\":\"Ashe\",\"win\":false}]}}"),
            mapper.readTree("{\"info\":{\"queueId\":440,\"participants\":[{\"puuid\":\"me\",\"championName\":\"Swain\",\"win\":true}]}}"),
            mapper.readTree("{\"info\":{\"queueId\":420,\"participants\":[{\"puuid\":\"me\",\"championName\":\"Swain\",\"win\":true,\"gameEndedInEarlySurrender\":true}]}}"));
        var result = RiotStats.summarize("me", matches);
        assertEquals(3, result.games());
        assertEquals(2, result.champions().size());
        assertEquals("Ashe", result.champions().getFirst().id());
        assertEquals(1, result.champions().getFirst().wins());
        assertEquals(50.0, result.champions().getFirst().winRate());
        assertEquals(java.util.Map.of("420",2,"440",1), result.modeGames());
    }
    @Test void includesNormalDraftAndRankedFivesButNotAramClashOrBots() {
        var matches = java.util.stream.IntStream.of(400,710,450,700,830,490).mapToObj(queue -> mapper.readTree(
            "{\"info\":{\"queueId\":"+queue+",\"participants\":[{\"puuid\":\"me\",\"championName\":\"Ashe\",\"win\":true}]}}" )).toList();
        assertEquals(2, RiotStats.summarize("me",matches).games());
    }
}
