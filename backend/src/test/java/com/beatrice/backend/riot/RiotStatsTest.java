package com.beatrice.backend.riot;

import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class RiotStatsTest {
    final ObjectMapper mapper = new ObjectMapper();
    @Test void countsOnlyThisPlayersSoloGamesAndExcludesRemakes() {
        var matches = List.of(
            mapper.readTree("{\"info\":{\"queueId\":420,\"participants\":[{\"puuid\":\"me\",\"championName\":\"Ashe\",\"win\":true},{\"puuid\":\"other\",\"championName\":\"Swain\",\"win\":false}]}}"),
            mapper.readTree("{\"info\":{\"queueId\":420,\"participants\":[{\"puuid\":\"me\",\"championName\":\"Ashe\",\"win\":false}]}}"),
            mapper.readTree("{\"info\":{\"queueId\":440,\"participants\":[{\"puuid\":\"me\",\"championName\":\"Swain\",\"win\":true}]}}"),
            mapper.readTree("{\"info\":{\"queueId\":420,\"participants\":[{\"puuid\":\"me\",\"championName\":\"Swain\",\"win\":true,\"gameEndedInEarlySurrender\":true}]}}"));
        var result = RiotStats.summarize("me", matches);
        assertEquals(2, result.games());
        assertEquals(1, result.champions().size());
        assertEquals("Ashe", result.champions().getFirst().id());
        assertEquals(1, result.champions().getFirst().wins());
        assertEquals(50.0, result.champions().getFirst().winRate());
    }
}
