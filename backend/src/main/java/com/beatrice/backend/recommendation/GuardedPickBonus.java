package com.beatrice.backend.recommendation;

import java.util.*;

/** Exact saved-scenario policy. Raw LambdaRank values are preferences, never probabilities. */
public final class GuardedPickBonus {
    public static final double CAP=2.5;
    public record Base(String championId,double score) {}
    public record Signal(String championId,double score,long globalGames,long recent30Picks,long patchGames,boolean seenInTrainingHistory) {
        boolean supported() {return seenInTrainingHistory && globalGames>=30 && recent30Picks>=5 && patchGames>=30;}
    }
    public record Pick(String championId,double javaScore,double mlBonus,double score,String mlEvidenceQuality) {}
    public record Result(List<Pick> picks,List<String> mlRanking,String status) {}
    private GuardedPickBonus() {}
    public static Result fallback(List<Base> bases,String reason) {
        return new Result(bases.stream().map(b->new Pick(b.championId(),b.score(),0,b.score(),reason)).toList(),List.of(),reason);
    }
    public static Result apply(List<Base> bases,List<Signal> signals) {
        var expected=new HashSet<String>();bases.forEach(b->expected.add(b.championId()));
        if(signals==null || signals.size()!=bases.size()) return fallback(bases,"INVALID_RESPONSE");
        var byId=new HashMap<String,Signal>();
        for(var s:signals) {
            if(s==null || !expected.contains(s.championId()) || byId.put(s.championId(),s)!=null
                || !Double.isFinite(s.score()) || s.globalGames()<0 || s.recent30Picks()<0 || s.patchGames()<0)
                return fallback(bases,"INVALID_RESPONSE");
        }
        var ordered=signals.stream().sorted(Comparator.comparingDouble(Signal::score).thenComparing(Signal::championId)).toList();
        var bonuses=new HashMap<String,Double>();
        boolean spread=ordered.size()>1 && ordered.getFirst().score()!=ordered.getLast().score();
        for(int i=0;i<ordered.size();i++) {
            var s=ordered.get(i);
            // All candidates, including unsupported ones, remain in the denominator.
            bonuses.put(s.championId(),spread && s.supported()?CAP*i/(ordered.size()-1):0.);
        }
        var picks=bases.stream().map(b->{
            double bonus=bonuses.get(b.championId());
            return new Pick(b.championId(),b.score(),bonus,b.score()+bonus,byId.get(b.championId()).supported()?"SUPPORTED":"INSUFFICIENT_EVIDENCE");
        }).sorted(Comparator.comparingDouble(Pick::score).reversed().thenComparing(Pick::championId)).toList();
        // Diagnostic rank uses descending score then ID, as in the accepted experiment.
        var ranking=signals.stream().sorted(Comparator.comparingDouble(Signal::score).reversed().thenComparing(Signal::championId)).map(Signal::championId).toList();
        return new Result(picks,ranking,"VALID");
    }
}
