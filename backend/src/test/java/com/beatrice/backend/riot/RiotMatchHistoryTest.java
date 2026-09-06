package com.beatrice.backend.riot;

import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

class RiotMatchHistoryTest {
    final ObjectMapper mapper = new ObjectMapper();
    @Test void pagesPastUnrelatedGamesAndStopsAtOneHundredEligibleGames() {
        var fetched = new ArrayList<String>();
        var result = RiotMatchHistory.collect("me",path -> {
            if (path.contains("/ids?")) {
                int start = path.contains("start=100&") ? 100 : 0;
                return mapper.valueToTree(java.util.stream.IntStream.range(start,start+100).mapToObj(i -> "NA1_"+i).toList());
            }
            fetched.add(path);
            int number = Integer.parseInt(path.substring(path.lastIndexOf('_')+1));
            return mapper.readTree("{\"info\":{\"queueId\":"+(number < 20 ? 450 : 400)+",\"participants\":[{\"puuid\":\"me\",\"championName\":\"Ashe\",\"win\":true}]}}");
        },(scanned,eligible) -> {});
        assertEquals(100,result.matches().size());
        assertEquals(120,result.scanned());
        assertFalse(result.limited());
        assertEquals(120,fetched.size());
    }
    @Test void emptyHistoryAndScanCapAreExplicit() {
        var empty = RiotMatchHistory.collect("me",path -> mapper.readTree("[]"),(s,e)->{});
        assertEquals(0,empty.scanned());
        assertFalse(empty.limited());
        var result = RiotMatchHistory.collect("me",path -> {
            if(path.contains("/ids?")) {
                int start = path.contains("start=200&") ? 200 : path.contains("start=100&") ? 100 : 0;
                return mapper.valueToTree(java.util.stream.IntStream.range(start,start+100).mapToObj(i -> "NA1_"+i).toList());
            }
            return mapper.readTree("{\"info\":{\"queueId\":450,\"participants\":[]}}");
        },(s,e)->{});
        assertEquals(300,result.scanned());
        assertTrue(result.limited());
    }
}
