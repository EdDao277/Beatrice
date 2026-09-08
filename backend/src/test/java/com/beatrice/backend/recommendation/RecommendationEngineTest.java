package com.beatrice.backend.recommendation;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import static com.beatrice.backend.recommendation.RecommendationEngine.*;

class RecommendationEngineTest {
    private final RecommendationEngine engine=new RecommendationEngine();
    private Champion champion(String id,int comfort,String...traits) {return new Champion(id,comfort,Set.of(traits));}
    private Context context(List<Champion> pool,List<Evidence> evidence) {
        return new Context("MID",pool,Set.of(),Set.of(),Set.of(),Set.of(),Map.of(),Map.of(),evidence);
    }
    @Test void comfortIsTheFallbackAndNoEvidenceProducesNoBans() {
        var result=engine.recommend(context(List.of(champion("Swain",10),champion("Orianna",6)),List.of()));
        assertEquals("Swain",result.picks().getFirst().championId());
        assertTrue(result.bans().isEmpty());
        assertTrue(result.picks().getFirst().warnings().contains("No role statistics for this evidence slice."));
    }
    @Test void unavailableAndProtectedPicksCannotBecomeBans() {
        var evidence=List.of(new Evidence("ROLE","Ahri","MID","","",100,70),new Evidence("ROLE","Zed","MID","","",100,70));
        var context=new Context("MID",List.of(champion("Ahri",10)),Set.of("Ahri"),Set.of("Zed"),Set.of(),Set.of(),Map.of(),Map.of(),evidence);
        var result=engine.recommend(context);
        assertTrue(result.picks().isEmpty()); assertTrue(result.bans().isEmpty());
    }
    @Test void tinySamplesCannotOverruleComfortAndUnknownRolesDoNotActivateMatchups() {
        var evidence=List.of(new Evidence("ROLE","Orianna","MID","","",1,1),new Evidence("MATCHUP","Orianna","MID","Zed","MID",100,100));
        var result=engine.recommend(context(List.of(champion("Swain",10),champion("Orianna",6)),evidence));
        assertEquals("Swain",result.picks().getFirst().championId());
        assertEquals(0,result.picks().get(1).contributions().get("matchup"));
    }
    @Test void bansUseCountersToExplicitIntendedPicks() {
        var evidence=List.of(new Evidence("MATCHUP","Swain","MID","Zed","MID",100,20));
        var context=new Context("MID",List.of(champion("Swain",10)),Set.of(),Set.of("Swain"),Set.of(),Set.of(),Map.of(),Map.of(),evidence);
        assertEquals("Zed",engine.recommend(context).bans().getFirst().championId());
    }
    @Test void reportsReproducibleContributionsAndCompositionCoverage() {
        var context=new Context("MID",List.of(champion("Swain",10,"AP","Frontline")),Set.of(),Set.of(),Set.of("AP","Frontline"),Set.of("Frontline"),Map.of(),Map.of(),List.of());
        var pick=engine.recommend(context).picks().getFirst();
        assertEquals(5,pick.contributions().get("composition"));
        assertEquals(pick.score(),pick.contributions().values().stream().mapToDouble(Double::doubleValue).sum());
    }
    @Test void synergyIsLimitedByTheWeakestBaselineSample() {
        var rows=List.of(new Evidence("ROLE","Swain","MID","","",100,50),
            new Evidence("ROLE","JarvanIV","JUNGLE","","",1,0),
            new Evidence("SYNERGY","Swain","MID","JarvanIV","JUNGLE",100,80));
        var c=new Context("MID",List.of(champion("Swain",10)),Set.of("JarvanIV"),Set.of(),Set.of(),Set.of(),Map.of("JarvanIV","JUNGLE"),Map.of(),rows);
        assertEquals(5.5/51,engine.recommend(c).picks().getFirst().contributions().get("synergy"),0.000001);
    }
    @Test void stableTiesReturnAtMostThreeCandidates() {
        var result=engine.recommend(context(List.of(champion("Zed",5),champion("Swain",5),champion("Ahri",5),champion("Orianna",5)),List.of()));
        assertEquals(List.of("Ahri","Orianna","Swain"),result.picks().stream().map(Candidate::championId).toList());
    }
    @Test void insufficientBanEvidenceAbstainsAndDuplicateEvidenceIsRejected() {
        var row=new Evidence("ROLE","Zed","MID","","",29,29);
        assertTrue(engine.recommend(context(List.of(),List.of(row))).bans().isEmpty());
        assertThrows(IllegalArgumentException.class,()->context(List.of(),List.of(row,row)));
    }
}
