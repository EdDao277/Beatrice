package com.beatrice.backend.recommendation;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class GuardedPickBonusTest {
    private GuardedPickBonus.Signal signal(String id,double score,boolean seen) {
        return new GuardedPickBonus.Signal(id,score,30,5,30,seen);
    }
    @Test void matchesOfflinePercentileIncludingUnsupportedDenominatorAndTies() {
        var bases=List.of(new GuardedPickBonus.Base("A",80),new GuardedPickBonus.Base("B",80),new GuardedPickBonus.Base("C",80));
        var result=GuardedPickBonus.apply(bases,List.of(signal("A",1,true),signal("B",1,false),signal("C",3,true)));
        assertEquals("C",result.picks().getFirst().championId());
        assertEquals(2.5,result.picks().getFirst().mlBonus());
        assertEquals(0,result.picks().stream().filter(p->p.championId().equals("B")).findFirst().orElseThrow().mlBonus());
        var tied=GuardedPickBonus.apply(bases,List.of(signal("A",1,true),signal("B",1,true),signal("C",3,true)));
        assertEquals(1.25,tied.picks().stream().filter(p->p.championId().equals("B")).findFirst().orElseThrow().mlBonus());
    }
    @Test void capCannotOvercomeLargeJavaDifferenceAndComfortBaseIsUntouched() {
        var result=GuardedPickBonus.apply(List.of(new GuardedPickBonus.Base("A",84),new GuardedPickBonus.Base("B",80)),List.of(signal("A",0,true),signal("B",99,true)));
        assertEquals("A",result.picks().getFirst().championId());
        assertEquals(84,result.picks().getFirst().javaScore());
        assertEquals(82.5,result.picks().get(1).score());
    }
    @Test void malformedSignalsFallBackWholeRequestAndColdCandidatesRemain() {
        var bases=List.of(new GuardedPickBonus.Base("A",80),new GuardedPickBonus.Base("COLD",79));
        for(var signals:List.of(List.of(signal("A",2,true),signal("OUTSIDE",5,true)),List.of(signal("A",Double.NaN,true),signal("COLD",1,true)),List.of(signal("A",1,true),signal("A",2,true)))) {
            var result=GuardedPickBonus.apply(bases,signals);
            assertEquals(List.of(80.,79.),result.picks().stream().map(GuardedPickBonus.Pick::score).toList());
            assertTrue(result.picks().stream().allMatch(p->p.mlBonus()==0));
        }
        var cold=GuardedPickBonus.apply(bases,List.of(signal("A",0,true),signal("COLD",100,false)));
        assertEquals(79,cold.picks().get(1).score());
        assertEquals("INSUFFICIENT_EVIDENCE",cold.picks().get(1).mlEvidenceQuality());
    }
    @Test void singletonAndEqualRawScoresReceiveNoBonus() {
        assertEquals(0,GuardedPickBonus.apply(List.of(new GuardedPickBonus.Base("A",80)),List.of(signal("A",3,true))).picks().getFirst().mlBonus());
        var result=GuardedPickBonus.apply(List.of(new GuardedPickBonus.Base("A",80),new GuardedPickBonus.Base("B",79)),List.of(signal("A",3,true),signal("B",3,true)));
        assertTrue(result.picks().stream().allMatch(p->p.mlBonus()==0));
    }
}
