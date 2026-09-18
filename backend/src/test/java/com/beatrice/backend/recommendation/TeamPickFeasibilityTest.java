package com.beatrice.backend.recommendation;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class TeamPickFeasibilityTest {
    @Test void backtracksInsteadOfCommittingFirstMatchingPlayer() {
        var pools=Map.of("TOP",Set.of("A","B"),"MID",Set.of("A"));
        var result=TeamPickFeasibility.candidates(pools,List.of("A"),Set.of("A"));
        assertEquals(Map.of("B",Set.of("TOP")),result);
    }
    @Test void retainsEveryFeasiblePlayerAndRejectsHallConflict() {
        var pools=Map.of("TOP",Set.of("A","B","C"),"MID",Set.of("A","B"),"BOT",Set.of("D"));
        assertEquals(Set.of("TOP","MID"),TeamPickFeasibility.candidates(pools,List.of(),Set.of()).get("A"));
        assertFalse(TeamPickFeasibility.candidates(pools,List.of("A","B"),Set.of("A","B")).containsKey("C"));
        assertEquals(Set.of("BOT"),TeamPickFeasibility.candidates(pools,List.of("A","B"),Set.of("A","B")).get("D"));
    }
    @Test void unavailableAndUnknownPicksNeverBecomeLegalThroughMissingEvidence() {
        var pools=Map.of("TOP",Set.of("COLD","BANNED"));
        assertEquals(Map.of("COLD",Set.of("TOP")),TeamPickFeasibility.candidates(pools,List.of(),Set.of("BANNED")));
        assertTrue(TeamPickFeasibility.candidates(pools,List.of("OUTSIDE"),Set.of("OUTSIDE")).isEmpty());
    }
}
