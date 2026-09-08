package com.beatrice.backend.recommendation;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static com.beatrice.backend.recommendation.RecommendationEngine.*;
class WeightedRecommendationTest {
    @Test void missingEvidenceIsNeutralAndCoverageIsSeparate() {
        var c=new Context("MID",List.of(new Champion("Swain",8,Set.of())),Set.of(),Set.of(),Set.of(),Set.of(),Map.of(),Map.of(),List.of());
        var pick=new WeightedRecommendations().score(c,Set.of()).getFirst();
        assertEquals(60.5,pick.score(),0.000001);
        assertEquals(35,pick.coverage(),0.000001);
        assertEquals(50,pick.components().get("synergy").value());
        assertFalse(pick.components().get("synergy").available());
    }
    @Test void knownUnmetCompositionIsDifferentFromUnknownAndAllCandidatesAreRanked() {
        var pool=List.of(new Champion("A",8,Set.of()),new Champion("B",8,Set.of()),new Champion("C",8,Set.of()),new Champion("D",7,Set.of("AP")));
        var context=new Context("MID",pool,Set.of(),Set.of(),Set.of("AP"),Set.of(),Map.of(),Map.of(),List.of());
        var scores=new WeightedRecommendations().score(context,Set.of("A","B","C","D"));
        assertEquals("D",scores.getFirst().championId());
        assertEquals(100,scores.getFirst().components().get("composition").value());
        assertEquals(0,scores.get(1).components().get("composition").value());
        assertTrue(scores.stream().allMatch(p->p.score()>=0 && p.score()<=100));
    }
}
