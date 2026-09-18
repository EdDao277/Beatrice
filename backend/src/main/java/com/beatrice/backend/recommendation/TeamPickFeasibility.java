package com.beatrice.backend.recommendation;

import java.util.*;

/** Saved membership only: evidence, comfort and pick order cannot make a pick illegal. */
public final class TeamPickFeasibility {
    private TeamPickFeasibility() {}
    public static Map<String,Set<String>> candidates(Map<String,Set<String>> pools,List<String> picks,Set<String> unavailable) {
        var result=new TreeMap<String,Set<String>>();
        if(picks.size()>=pools.size() || new HashSet<>(picks).size()!=picks.size()) return result;
        var union=new TreeSet<String>();pools.values().forEach(union::addAll);
        union.removeAll(unavailable);union.removeAll(picks);
        for(String champion:union) {
            var feasible=new TreeSet<String>();
            for(var player:pools.entrySet()) if(player.getValue().contains(champion)
                && match(pools,picks,0,new HashSet<>(Set.of(player.getKey())))) feasible.add(player.getKey());
            if(!feasible.isEmpty()) result.put(champion,Collections.unmodifiableSet(feasible));
        }
        return Collections.unmodifiableMap(result);
    }
    private static boolean match(Map<String,Set<String>> pools,List<String> picks,int index,Set<String> used) {
        if(index==picks.size()) return true;
        for(var player:pools.entrySet()) if(!used.contains(player.getKey()) && player.getValue().contains(picks.get(index))) {
            used.add(player.getKey());
            boolean complete=match(pools,picks,index+1,used);
            used.remove(player.getKey());
            if(complete) return true;
        }
        return false;
    }
}
