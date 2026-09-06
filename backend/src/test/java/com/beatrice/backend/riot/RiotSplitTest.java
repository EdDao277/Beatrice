package com.beatrice.backend.riot;

import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

class RiotSplitTest {
    final ObjectMapper mapper = new ObjectMapper();
    @Test void highestRankUsesTierDivisionThenLpAndExcludesClassic() {
        var ranks = mapper.readTree("""
            [{"queueType":"JADE_RANKED_SOLO_5x5","tier":"CHALLENGER","rank":"I","leaguePoints":999},
             {"queueType":"RANKED_SOLO_5x5","tier":"DIAMOND","rank":"III","leaguePoints":59},
             {"queueType":"RANKED_PREMADE_5x5","tier":"DIAMOND","rank":"I","leaguePoints":53}]
            """);
        assertEquals("Ranked 5s", RiotRanks.highest(ranks).mode());
        assertEquals(53, RiotRanks.highest(ranks).lp());
        assertNull(RiotRanks.highest(mapper.readTree("[]")));
    }
    @Test void aggregationKeepsAllChampionsAndCombinedWins() {
        var matches = new ArrayList<tools.jackson.databind.JsonNode>();
        for (String name : List.of("Ashe","Jinx","Lux","Zed")) matches.add(mapper.readTree(
            "{\"info\":{\"queueId\":400,\"participants\":[{\"puuid\":\"me\",\"championName\":\""+name+"\",\"win\":true}]}}"));
        var sample = RiotStats.summarize("me",matches);
        assertEquals(4,sample.champions().size());
        assertEquals(4,sample.wins());
    }
    @Test void masteryOrdersByPointsAndKeepsOnlyThree() {
        var entries = mapper.readTree("""
            [{"championId":1,"championLevel":2,"championPoints":10},
             {"championId":2,"championLevel":3,"championPoints":40},
             {"championId":3,"championLevel":4,"championPoints":20},
             {"championId":4,"championLevel":5,"championPoints":30}]
            """);
        var top = RiotMastery.top(entries,id -> "champ"+id);
        assertEquals(List.of("champ2","champ4","champ3"),top.stream().map(RiotMastery.Champion::id).toList());
        assertEquals(40,top.getFirst().points());
    }
}
