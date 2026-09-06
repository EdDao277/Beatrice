package com.beatrice.backend.riot;

import java.util.*;
import tools.jackson.databind.JsonNode;

/** Compare official current ranks only; this is not an MMR estimate. */
public final class RiotRanks {
    private RiotRanks() {}
    private static final List<String> TIERS = List.of("IRON","BRONZE","SILVER","GOLD","PLATINUM","EMERALD","DIAMOND","MASTER","GRANDMASTER","CHALLENGER");
    private static final List<String> DIVISIONS = List.of("IV","III","II","I");
    private static final Map<String,String> MODES = Map.of("RANKED_SOLO_5x5","Solo/Duo","RANKED_FLEX_SR","Flex","RANKED_PREMADE_5x5","Ranked 5s");
    public record Rank(String tier,String division,int lp,String mode) {}
    public static Rank highest(JsonNode leagues) {
        var ranks = new ArrayList<Rank>();
        for (var league : leagues) {
            String mode = MODES.get(league.path("queueType").asString());
            String tier = league.path("tier").asString();
            String division = league.path("rank").asString();
            if (mode != null && TIERS.contains(tier) && DIVISIONS.contains(division))
                ranks.add(new Rank(tier,division,league.path("leaguePoints").asInt(),mode));
        }
        return ranks.stream().max(Comparator.comparingInt((Rank r) -> TIERS.indexOf(r.tier()))
            .thenComparingInt(r -> DIVISIONS.indexOf(r.division())).thenComparingInt(Rank::lp).thenComparing(Rank::mode)).orElse(null);
    }
}
