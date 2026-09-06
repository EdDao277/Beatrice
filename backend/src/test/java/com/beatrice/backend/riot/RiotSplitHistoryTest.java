package com.beatrice.backend.riot;

import com.beatrice.backend.TestDatabase;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest @Import(TestDatabase.class) @Transactional
class RiotSplitHistoryTest {
    @Autowired RiotSplitHistory history;
    @Autowired ObjectMapper mapper;
    @Test void failedDownloadDoesNotAdvanceCursorAndRetryReusesEvidence() {
        var start=Instant.parse("2026-07-29T19:00:00Z");
        var end=Instant.parse("2026-09-06T00:00:00Z");
        var match=mapper.readTree("{\"info\":{\"gameStartTimestamp\":1788105600000,\"queueId\":400,\"participants\":[{\"puuid\":\"retry\",\"championName\":\"Ashe\",\"win\":true}]}}");
        assertThrows(IllegalStateException.class,()->history.sync("retry",start,end,path->{
            if(path.contains("/ids?")) return mapper.readTree("[\"NA1_a\",\"NA1_b\"]");
            if(path.endsWith("NA1_b")) throw new IllegalStateException("Fixture interruption");
            return match;
        },n->{}));
        var result=history.sync("retry",start,end,path->{
            if(path.contains("/ids?")) {
                assertTrue(path.contains("startTime="+start.getEpochSecond()),"Failed import must retry the original window");
                return mapper.readTree("[\"NA1_a\",\"NA1_b\"]");
            }
            assertTrue(path.endsWith("NA1_b"),"First persisted match should be reused");
            return match;
        },n->{});
        assertTrue(result.complete());
        assertEquals(2,result.sample().games());
    }
    @Test void cappedImportCanResumeWithoutCountingCachedMatchesTwice() {
        var start = Instant.parse("2026-07-29T19:00:00Z");
        var end = Instant.parse("2026-09-06T00:00:00Z");
        java.util.function.Function<String,tools.jackson.databind.JsonNode> fetch = path -> {
            if (path.contains("/ids?")) {
                int offset = Integer.parseInt(path.split("start=")[1].split("&")[0]);
                return mapper.valueToTree(java.util.stream.IntStream.range(offset,Math.min(offset+100,301)).mapToObj(i->"NA1_cap"+i).toList());
            }
            return mapper.readTree("{\"info\":{\"gameStartTimestamp\":1788105600000,\"queueId\":710,\"participants\":[{\"puuid\":\"cap\",\"championName\":\"Ashe\",\"win\":true}]}}");
        };
        var first=history.sync("cap",start,end,fetch,n->{});
        assertFalse(first.complete());
        assertEquals(300,first.sample().games());
        var second=history.sync("cap",start,end,fetch,n->{});
        assertTrue(second.complete());
        assertEquals(301,second.sample().games());
    }
    @Test void cachedMatchesAreReusedAndDuplicateIdsCountOnce() {
        var start = Instant.parse("2026-07-29T19:00:00Z");
        var end = Instant.parse("2026-09-06T00:00:00Z");
        var first = history.sync("fixture",start,end,path -> path.contains("/ids?")
            ? mapper.readTree("[\"NA1_fixture\",\"NA1_fixture\"]")
            : mapper.readTree("{\"info\":{\"gameStartTimestamp\":1788105600000,\"queueId\":400,\"participants\":[{\"puuid\":\"fixture\",\"championName\":\"Ashe\",\"win\":true}]}}"),n -> {});
        assertTrue(first.complete());
        assertEquals(1,first.sample().games());
        assertEquals(1,first.sample().wins());
        var second = history.sync("fixture",start,end,path -> {
            assertTrue(path.contains("/ids?"),"Cached match must not be downloaded again");
            return mapper.readTree("[\"NA1_fixture\"]");
        },n -> {});
        assertEquals(1,second.sample().games());
        assertTrue(second.complete());
    }
}
