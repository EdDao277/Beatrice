package com.beatrice.backend.recommendation;
import java.util.*;
import static com.beatrice.backend.recommendation.RecommendationEngine.*;

/** Fixed weights: unavailable factors remain neutral, never redistributed between candidates. */
public final class WeightedRecommendations {
    public record Component(double value,int weight,boolean available,String explanation) {}
    public record Pick(String championId,double score,double coverage,Map<String,Component> components,List<String> warnings,List<Evidence> evidence) {}
    public List<Pick> score(Context context,Set<String> knownMetadata) {
        var result=new ArrayList<Pick>();var engine=new RecommendationEngine();
        // Compute pick evidence once; do not recalculate every ban for each pool champion.
        var baselines=new HashMap<String,Candidate>();
        engine.scorePicks(context).forEach(p->baselines.put(p.championId(),p));
        for(var champion:context.pool()) {
            if(context.unavailable().contains(champion.id())) continue;
            var baseline=baselines.get(champion.id());
            var components=new LinkedHashMap<String,Component>();
            components.put("comfort",new Component(champion.comfort()*10,35,true,"Saved player comfort."));
            var needed=new HashSet<>(context.desiredTraits());needed.removeAll(context.coveredTraits());
            var supplied=new HashSet<>(champion.traits());supplied.retainAll(needed);
            boolean composition=knownMetadata.contains(champion.id()) && !needed.isEmpty();
            components.put("composition",new Component(composition?100.0*supplied.size()/needed.size():50,20,composition,"Coverage of explicitly requested, uncovered traits; unknown otherwise."));
            boolean role=baseline.evidence().stream().anyMatch(e->e.kind().equals("ROLE") && e.championId().equals(champion.id()) && e.role().equals(context.targetRole()));
            for(String kind:List.of("synergy","matchup")) {
                boolean available=role && baseline.evidence().stream().anyMatch(e->e.kind().equals(kind.toUpperCase(Locale.ROOT)));
                components.put(kind,new Component(available?Math.max(0,Math.min(100,50+baseline.contributions().get(kind)*10)):50,kind.equals("synergy")?15:10,available,"Sample-weighted role-specific observations; unknown roles are not inferred."));
            }
            components.put("meta",new Component(role?Math.max(0,Math.min(100,50+baseline.contributions().get("role")*10)):50,8,role,"Selected collection's role results, not professional-game evidence."));
            components.put("teamHistory",new Component(50,7,false,"Team-history component not implemented; neutral."));
            components.put("draftValue",new Component(50,5,false,"Draft-value component not implemented; neutral."));
            double score=components.values().stream().mapToDouble(c->c.value()*c.weight()/100).sum();
            double coverage=components.values().stream().filter(Component::available).mapToInt(Component::weight).sum();
            result.add(new Pick(champion.id(),score,coverage,Collections.unmodifiableMap(components),baseline.warnings(),baseline.evidence()));
        }
        return result.stream().sorted(Comparator.comparingDouble(Pick::score).reversed().thenComparing(Pick::championId)).limit(3).toList();
    }
}
