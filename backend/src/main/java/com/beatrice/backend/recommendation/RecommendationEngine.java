package com.beatrice.backend.recommendation;

import java.util.*;

/** Pure baseline: scores are preference points, never win probabilities or learned weights. */
public final class RecommendationEngine {
    private static final Set<String> ROLES=Set.of("TOP","JUNGLE","MID","BOT","SUPPORT");
    public record Champion(String id,int comfort,Set<String> traits) {
        public Champion { if(id==null || id.isBlank() || comfort<1 || comfort>10) throw new IllegalArgumentException("Invalid pool champion"); traits=Set.copyOf(traits); }
    }
    /** All rows supplied in one call must come from ONE dataset, patch and queue slice. */
    public record Evidence(String kind,String championId,String role,String partnerId,String partnerRole,long games,long wins) {
        public Evidence {
            if(!Set.of("ROLE","SYNERGY","MATCHUP").contains(kind) || championId==null || championId.isBlank() || !ROLES.contains(role)
                || games<=0 || wins<0 || wins>games || partnerId==null || partnerRole==null
                || (!kind.equals("ROLE") && (partnerId.isBlank() || !ROLES.contains(partnerRole)))) throw new IllegalArgumentException("Invalid evidence");
        }
        double rate() {return (double)wins/games;}
        double reliability() {return (double)games/(games+50.0);}
    }
    /** Role maps contain explicitly assigned champions only. Unresolved picks are absent.
     * Desired traits are explicit team needs; the engine does not guess them from missing data.
     */
    public record Context(String targetRole,List<Champion> pool,Set<String> unavailable,Set<String> intendedPicks,
        Set<String> desiredTraits,Set<String> coveredTraits,Map<String,String> allyRoles,Map<String,String> enemyRoles,List<Evidence> evidence) {
        public Context {
            if(!ROLES.contains(targetRole)) throw new IllegalArgumentException("Unknown target role");
            pool=List.copyOf(pool);unavailable=Set.copyOf(unavailable);intendedPicks=Set.copyOf(intendedPicks);
            desiredTraits=Set.copyOf(desiredTraits);coveredTraits=Set.copyOf(coveredTraits);
            allyRoles=Map.copyOf(allyRoles);enemyRoles=Map.copyOf(enemyRoles);evidence=List.copyOf(evidence);
            if(pool.stream().map(Champion::id).distinct().count()!=pool.size()) throw new IllegalArgumentException("Duplicate pool champion");
            for(var roles:List.of(allyRoles,enemyRoles)) {
                if(!ROLES.containsAll(roles.values()) || roles.values().stream().distinct().count()!=roles.size()) throw new IllegalArgumentException("Invalid role assignments");
                if(!unavailable.containsAll(roles.keySet())) throw new IllegalArgumentException("Assigned champions must be picked/unavailable");
            }
            var keys=new HashSet<List<String>>();
            for(var e:evidence) if(!keys.add(List.of(e.kind(),e.championId(),e.role(),e.partnerId(),e.partnerRole()))) throw new IllegalArgumentException("Duplicate evidence; do not merge source slices");
        }
    }
    public record Candidate(String championId,double score,Map<String,Double> contributions,List<String> reasons,List<String> warnings,List<Evidence> evidence) {}
    public record Result(List<Candidate> picks,List<Candidate> bans,String algorithm) {}

    public List<Candidate> scorePicks(Context c) {
        var picks=new ArrayList<Candidate>();
        for(var champion:c.pool()) {
            if(c.unavailable().contains(champion.id())) continue;
            var used=new ArrayList<Evidence>();var reasons=new ArrayList<String>();var warnings=new ArrayList<String>();
            var parts=new LinkedHashMap<String,Double>();
            parts.put("comfort",champion.comfort()*6.0); reasons.add("Saved comfort: "+champion.comfort()+"/10.");
            var needed=new TreeSet<>(champion.traits());needed.retainAll(c.desiredTraits());needed.removeAll(c.coveredTraits());
            parts.put("composition",Math.min(2,needed.size())*5.0);
            if(!needed.isEmpty()) reasons.add("Adds requested traits: "+String.join(", ",needed)+".");
            var baseline=role(c,champion.id(),c.targetRole());
            parts.put("role",baseline==null?0:bounded((baseline.rate()-.5)*10*baseline.reliability(),5));
            if(baseline!=null) used.add(baseline);else warnings.add("No role statistics for this evidence slice.");
            parts.put("synergy",pairScore(c,champion.id(),baseline,"SYNERGY",c.allyRoles(),used));
            parts.put("matchup",pairScore(c,champion.id(),baseline,"MATCHUP",c.enemyRoles(),used));
            if(c.allyRoles().isEmpty()) warnings.add("Ally roles unresolved or no allies assigned; no role-specific synergy adjustment.");
            if(c.enemyRoles().isEmpty()) warnings.add("Enemy roles unresolved or no enemies assigned; no role-specific matchup adjustment.");
            if(baseline!=null) reasons.add("Role and pair adjustments are bounded, sample-weighted observations.");
            picks.add(candidate(champion.id(),parts,reasons,warnings,used));
        }
        return List.copyOf(picks);
    }
    public Result recommend(Context c) {
        var picks=scorePicks(c);
        var bans=new ArrayList<Candidate>();var candidates=new TreeSet<String>();
        for(var e:c.evidence()) {
            if(e.kind().equals("ROLE")) candidates.add(e.championId());
            if(e.kind().equals("MATCHUP") && c.intendedPicks().contains(e.championId()) && e.role().equals(c.targetRole())) candidates.add(e.partnerId());
        }
        for(String id:candidates) {
            if(c.unavailable().contains(id) || c.intendedPicks().contains(id)) continue;
            var used=new ArrayList<Evidence>();var reasons=new ArrayList<String>();var warnings=new ArrayList<String>();
            double strength=0,threat=0;
            for(var e:c.evidence()) {
                // Sparse statistics may be shown for picks, but cannot establish a ban recommendation.
                if(e.games()<30) continue;
                if(e.kind().equals("ROLE") && e.championId().equals(id) && e.rate()>.5) {
                    strength=Math.max(strength,(e.rate()-.5)*10*e.reliability());used.add(e);
                }
                if(e.kind().equals("MATCHUP") && e.partnerId().equals(id) && e.role().equals(c.targetRole()) && e.partnerRole().equals(c.targetRole())
                    && c.intendedPicks().contains(e.championId()) && e.rate()<.5) {
                    threat=Math.max(threat,(.5-e.rate())*20*e.reliability());used.add(e);
                }
            }
            if(strength==0 && threat==0) continue;
            double cost=c.pool().stream().filter(p->p.id().equals(id)).mapToDouble(p->p.comfort()).max().orElse(0);
            var parts=new LinkedHashMap<String,Double>();parts.put("roleStrength",bounded(strength,5));parts.put("intendedPickThreat",bounded(threat,10));parts.put("ownPoolCost",-cost);
            if(parts.values().stream().mapToDouble(Double::doubleValue).sum()<=0) continue;
            if(threat>0) reasons.add("Observed unfavorable same-role matchup for an explicitly intended pick.");
            if(strength>0) reasons.add("Above-50% observed role results in the supplied slice; not an opponent preference prediction.");
            if(cost>0) reasons.add("Penalty for removing an option from the supplied player pool.");
            warnings.add("Opponent champion pools are unknown. Observational results do not establish causation.");
            bans.add(candidate(id,parts,reasons,warnings,used));
        }
        return new Result(top(picks),top(bans),"comfort-evidence-v1");
    }
    private Evidence role(Context c,String id,String role) {return c.evidence().stream().filter(e->e.kind().equals("ROLE") && e.championId().equals(id) && e.role().equals(role)).findFirst().orElse(null);}
    private double pairScore(Context c,String id,Evidence baseline,String kind,Map<String,String> assignments,List<Evidence> used) {
        if(baseline==null) return 0;
        double sum=0;int count=0;
        for(var e:c.evidence()) if(e.kind().equals(kind) && e.championId().equals(id) && e.role().equals(c.targetRole()) && e.partnerRole().equals(assignments.get(e.partnerId()))) {
            if(kind.equals("MATCHUP") && !e.partnerRole().equals(c.targetRole())) continue;
            double expected=baseline.rate();
            double reliability=Math.min(e.reliability(),baseline.reliability());
            if(kind.equals("SYNERGY")) {
                var ally=role(c,e.partnerId(),e.partnerRole());if(ally==null) continue;
                expected=(expected+ally.rate())/2;used.add(ally);
                reliability=Math.min(reliability,ally.reliability());
            }
            sum+=(e.rate()-expected)*10*reliability;count++;used.add(e);
        }
        return count==0?0:bounded(sum/count,5);
    }
    private Candidate candidate(String id,Map<String,Double> parts,List<String> reasons,List<String> warnings,List<Evidence> evidence) {
        if(evidence.stream().anyMatch(e->e.games()<30)) warnings.add("Small sample: fewer than 30 games. Weighting is a heuristic, not statistical confidence.");
        return new Candidate(id,parts.values().stream().mapToDouble(Double::doubleValue).sum(),Collections.unmodifiableMap(new LinkedHashMap<>(parts)),List.copyOf(reasons),List.copyOf(warnings),evidence.stream().distinct().toList());
    }
    private List<Candidate> top(List<Candidate> rows) {return rows.stream().sorted(Comparator.comparingDouble(Candidate::score).reversed().thenComparing(Candidate::championId)).limit(3).toList();}
    private double bounded(double value,double limit) {return Math.max(-limit,Math.min(limit,value));}
}
