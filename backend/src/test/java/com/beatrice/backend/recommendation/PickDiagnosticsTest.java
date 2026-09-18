package com.beatrice.backend.recommendation;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

class PickDiagnosticsTest {
    @TempDir Path folder;
    @Test void linksOnlyKnownTeamAndLegalCandidateAndContainsNoPlayerIdentity() throws Exception {
        var log=new PickDiagnostics(folder.toString(),new ObjectMapper());
        var bases=List.of(new GuardedPickBonus.Base("A",80));
        log.record("r",12,bases,GuardedPickBonus.fallback(bases,"ML_UNAVAILABLE"),10);
        assertFalse(log.selected("r",13,"A"));
        assertFalse(log.selected("r",12,"OUTSIDE"));
        assertTrue(log.selected("r",12,"A"));
        assertFalse(log.selected("r",12,"A"));
        var lines=Files.readAllLines(folder.resolve("picks.jsonl"));
        assertEquals(2,lines.size());
        var selection=new ObjectMapper().readTree(lines.get(1));
        assertEquals("A",selection.path("selectedChampionId").asString());
        assertFalse(selection.has("playerName"));
    }
    @Test void unwritableDestinationCannotBreakRecommendation() throws Exception {
        var file=folder.resolve("file");Files.writeString(file,"not a directory");
        var log=new PickDiagnostics(file.toString(),new ObjectMapper());
        assertDoesNotThrow(()->log.record("r",1,List.of(),GuardedPickBonus.fallback(List.of(),"EMPTY"),0));
    }
    @Test void recordsValidatedHistoryProvenance() throws Exception {
        var log=new PickDiagnostics(folder.toString(),new ObjectMapper());
        var bases=List.of(new GuardedPickBonus.Base("A",80));
        var inference=new PickModelClient.Result(List.of(new GuardedPickBonus.Signal("A",1,40,5,30,true)),"VALID",3,
            "refreshed-2026.09.17","aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb");
        log.record("r",12,bases,GuardedPickBonus.apply(bases,inference.signals()),inference);
        var event=new ObjectMapper().readTree(Files.readString(folder.resolve("picks.jsonl")));
        assertEquals("refreshed-2026.09.17",event.path("historyBundleVersion").asString());
        assertEquals("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",event.path("historyBundleSha256").asString());
        assertEquals("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",event.path("historySnapshotId").asString());
    }
}
