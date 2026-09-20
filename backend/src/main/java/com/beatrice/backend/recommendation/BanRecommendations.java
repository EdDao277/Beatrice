package com.beatrice.backend.recommendation;

import java.util.*;
import static com.beatrice.backend.recommendation.RecommendationEngine.*;

/** Ban-only policy. Curated threat hints are not measured matchup statistics. */
public final class BanRecommendations {
    public record Metadata(Set<String> counters,Set<String> counteredBy,Set<String> compTags,Set<String> counterTags) {}
    public record Ban(String championId,double score,String basis,Map<String,Double> contributions,
        Set<String> threatenedPicks,List<String> reasons,List<String> warnings,List<Evidence> evidence) {}
    private static final Comparator<Ban> ORDER=Comparator.comparingDouble(Ban::score).reversed().thenComparing(Ban::championId);

    public List<Ban> rank(Map<String,List<Champion>> pools,Map<String,Metadata> metadata,List<Evidence> evidence,
            Set<String> unavailable,Set<String> catalogIds) {
        var likely=new TreeMap<String,List<Champion>>();
        var own=new TreeMap<String,Champion>();
        pools.forEach((role,pool)->{
            for(var c:pool) own.merge(c.id(),c,(a,b)->a.comfort()>=b.comfort()?a:b);
            likely.put(role,pool.stream().filter(c->c.comfort()>=8 && !unavailable.contains(c.id()))
                .sorted(Comparator.comparingInt(Champion::comfort).reversed().thenComparing(Champion::id)).limit(3).toList());
        });
        var protectedIds=new HashSet<String>();
        likely.values().forEach(pool->pool.forEach(c->protectedIds.add(c.id())));
        var excluded=new HashSet<>(unavailable);excluded.addAll(protectedIds);

        var statistical=new HashMap<String,Ban>();
        var engine=new RecommendationEngine();
        for(var entry:likely.entrySet()) {
            var intended=new HashSet<String>();entry.getValue().forEach(c->intended.add(c.id()));
            var context=new Context(entry.getKey(),List.copyOf(own.values()),excluded,intended,Set.of(),Set.of(),Map.of(),Map.of(),evidence);
            for(var candidate:engine.scoreBans(context)) {
                if(!catalogIds.contains(candidate.championId())) continue;
                var reasons=new ArrayList<String>();
                if(candidate.contributions().get("roleStrength")>0)
                    reasons.add("Above-50% observed role results in the selected reference slice.");
                if(candidate.contributions().get("intendedPickThreat")>0)
                    reasons.add("Observed same-role counter to a high-comfort pool option; this is a possible pick, not a confirmed lane.");
                if(candidate.contributions().get("ownPoolCost")<0) reasons.add("Penalized for removing your team's saved option.");
                var threatened=new TreeSet<String>();
                candidate.evidence().stream().filter(e->e.kind().equals("MATCHUP")).forEach(e->threatened.add(e.championId()));
                var ban=new Ban(candidate.championId(),candidate.score(),"EVIDENCE_BACKED",candidate.contributions(),Set.copyOf(threatened),
                    List.copyOf(reasons),candidate.warnings(),candidate.evidence());
                // Do not add scores across roles or count a flex hypothesis as independent evidence.
                statistical.merge(ban.championId(),ban,(a,b)->a.score()>=b.score()?a:b);
            }
        }
        var result=new ArrayList<>(statistical.values().stream().sorted(ORDER).limit(6).toList());
        if(result.size()==6)return List.copyOf(result);
        var fallback=new ArrayList<Ban>();
        for(String id:new TreeSet<>(catalogIds)) {
            if(excluded.contains(id) || statistical.containsKey(id))continue;
            var threat=metadata.get(id);
            var targetIds=new TreeSet<String>();var targetRoles=new TreeSet<String>();var reasons=new TreeSet<String>();
            for(var entry:likely.entrySet()) for(var target:entry.getValue()) {
                var targetMetadata=metadata.get(target.id());
                boolean direct=(threat!=null && threat.counters().contains(target.id()))
                    || (targetMetadata!=null && targetMetadata.counteredBy().contains(id));
                boolean composition=threat!=null && targetMetadata!=null && targetMetadata.compTags().stream()
                    .anyMatch(tag->threat.counterTags().contains("Counters"+tag));
                if(direct || composition) {
                    targetIds.add(target.id());targetRoles.add(entry.getKey());
                    if(direct)reasons.add("Curated counter relationship to likely pool option "+target.id()+".");
                    if(composition)reasons.add("Explicit composition-counter tag matches likely pool option "+target.id()+".");
                }
            }
            // A single flex champion must not masquerade as two independent likely picks.
            if(targetIds.size()<2 || targetRoles.size()<2)continue;
            double cost=own.containsKey(id)?own.get(id).comfort():0;
            var parts=new LinkedHashMap<String,Double>();
            parts.put("threatenedRosterRoles",2.0*targetRoles.size());
            parts.put("distinctLikelyPicks",.5*Math.min(4,targetIds.size()));
            parts.put("ownPoolCost",-cost);
            double score=parts.values().stream().mapToDouble(Double::doubleValue).sum();
            if(score<=0)continue;
            fallback.add(new Ban(id,score,"POOL_COMPOSITION_FALLBACK",Map.copyOf(parts),Set.copyOf(targetIds),List.copyOf(reasons),
                List.of("Lower-confidence curated pool/composition heuristic; no statistical support claimed.",
                    "Pool options are alternatives, not confirmed picks or lane assignments. Opponent pools are unknown."),List.of()));
        }
        result.addAll(fallback.stream().sorted(ORDER).limit(6-result.size()).toList());
        return List.copyOf(result);
    }
}
