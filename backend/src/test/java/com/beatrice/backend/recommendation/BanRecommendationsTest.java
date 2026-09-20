package com.beatrice.backend.recommendation;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static com.beatrice.backend.recommendation.RecommendationEngine.*;

class BanRecommendationsTest {
    private final BanRecommendations scorer=new BanRecommendations();
    private Champion champion(String id,int comfort) {return new Champion(id,comfort,Set.of());}
    private Map<String,List<Champion>> pools() {return Map.of("MID",List.of(champion("Mage",10)),"BOT",List.of(champion("Carry",9)));}
    private BanRecommendations.Metadata counter(String... targets) {
        return new BanRecommendations.Metadata(Set.of(targets),Set.of(),Set.of(),Set.of());
    }
    @Test void preservesStatisticalScoresAndReturnsSixRatherThanThree() {
        var evidence=new ArrayList<Evidence>();
        for(int i=0;i<8;i++) evidence.add(new Evidence("ROLE","Enemy"+i,"MID","","",100,70));
        var result=scorer.rank(pools(),Map.of(),evidence,Set.of("Enemy0"),Set.of("Enemy0","Enemy1","Enemy2","Enemy3","Enemy4","Enemy5","Enemy6","Enemy7"));
        assertEquals(List.of("Enemy1","Enemy2","Enemy3","Enemy4","Enemy5","Enemy6"),result.stream().map(BanRecommendations.Ban::championId).toList());
        assertTrue(result.stream().allMatch(b->b.basis().equals("EVIDENCE_BACKED")));
        assertEquals((.7-.5)*10*100/150,result.getFirst().score(),1e-9);
        assertEquals(100,result.getFirst().evidence().getFirst().games());
    }
    @Test void fallbackNeedsTwoDifferentLikelyChampionsAcrossTwoPlayersAndNeverFabricatesStats() {
        var metadata=Map.of("Threat",counter("Mage","Carry"),"Weak",counter("Mage"),"Unknown",counter());
        var result=scorer.rank(pools(),metadata,List.of(),Set.of(),metadata.keySet());
        assertEquals(1,result.size());assertEquals("Threat",result.getFirst().championId());
        assertEquals("POOL_COMPOSITION_FALLBACK",result.getFirst().basis());
        assertTrue(result.getFirst().evidence().isEmpty());
        assertEquals(Set.of("Mage","Carry"),result.getFirst().threatenedPicks());
        assertTrue(scorer.rank(Map.of("MID",List.of(champion("Mage",10),champion("Carry",9))),metadata,List.of(),Set.of(),metadata.keySet()).isEmpty());
    }
    @Test void exclusionsAndPoolCostApplyToBothTiers() {
        var metadata=Map.of("Threat",counter("Mage","Carry"),"Unavailable",counter("Mage","Carry"),"Uncatalogued",counter("Mage","Carry"));
        var roster=new HashMap<>(pools());roster.put("TOP",List.of(champion("Threat",7)));
        assertTrue(scorer.rank(roster,metadata,List.of(),Set.of("Unavailable"),Set.of("Threat","Unavailable")).isEmpty());
        var stats=List.of(new Evidence("ROLE","Mage","MID","","",100,90));
        assertTrue(scorer.rank(pools(),Map.of(),stats,Set.of(),Set.of("Mage")).isEmpty());
    }
    @Test void statisticalTierComesFirstAndFallbackDoesNotDuplicateIt() {
        var metadata=Map.of("Threat",counter("Mage","Carry"),"Other",counter("Mage","Carry"));
        var stats=List.of(new Evidence("ROLE","Threat","MID","","",30,16));
        var result=scorer.rank(pools(),metadata,stats,Set.of(),metadata.keySet());
        assertEquals(List.of("Threat","Other"),result.stream().map(BanRecommendations.Ban::championId).toList());
        assertEquals("EVIDENCE_BACKED",result.getFirst().basis());
        assertEquals("POOL_COMPOSITION_FALLBACK",result.getLast().basis());
    }
    @Test void compositionUsesExplicitCounterTagsNotMissingMetadataOrAssumedLanes() {
        var metadata=Map.of("Mage",new BanRecommendations.Metadata(Set.of(),Set.of(),Set.of("FrontToBack"),Set.of()),
            "Carry",new BanRecommendations.Metadata(Set.of(),Set.of(),Set.of("FrontToBack"),Set.of()),
            "Threat",new BanRecommendations.Metadata(Set.of(),Set.of(),Set.of(),Set.of("CountersFrontToBack")));
        assertEquals("Threat",scorer.rank(pools(),metadata,List.of(),Set.of(),Set.of("Threat")).getFirst().championId());
        assertTrue(scorer.rank(pools(),Map.of("Threat",metadata.get("Threat")),List.of(),Set.of(),Set.of("Threat")).isEmpty());
        assertTrue(scorer.rank(Map.of("MID",List.of(champion("Mage",7)),"BOT",List.of(champion("Carry",7))),metadata,List.of(),Set.of(),Set.of("Threat")).isEmpty());
    }
    @Test void sparseStatsAloneCannotCreateBansAndFallbackStopsAtSix() {
        assertTrue(scorer.rank(pools(),Map.of(),List.of(new Evidence("ROLE","Threat","MID","","",29,29)),Set.of(),Set.of("Threat")).isEmpty());
        var metadata=new TreeMap<String,BanRecommendations.Metadata>();
        for(int i=0;i<8;i++)metadata.put("Threat"+i,counter("Mage","Carry"));
        assertEquals(6,scorer.rank(pools(),metadata,List.of(),Set.of(),metadata.keySet()).size());
    }
}
