package com.beatrice.backend.collection;

import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.*;

/** Match ledger and all aggregate increments commit together. Replays are harmless. */
@Service
public class CollectionStats {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    public CollectionStats(JdbcTemplate jdbc,ObjectMapper mapper) {this.jdbc=jdbc;this.mapper=mapper;}
    private record Player(String champion,String role,int team,boolean win) {}
    private static final Set<String> TABLES=Set.of("champion_role_stats","champion_synergy_stats","champion_matchup_stats","team_comp_signature_stats");
    @Transactional
    public boolean accept(String dataset,String id,JsonNode match,long start,long end,List<Integer> queues,long metadataImport) {
        var info=match.path("info");
        long timestamp=info.path("gameStartTimestamp").asLong(0)/1000;
        String version=info.path("gameVersion").asString();
        int queue=info.path("queueId").asInt();
        var players=new ArrayList<Player>();
        boolean valid=timestamp>=start && timestamp<end && queues.contains(queue) && version.matches("[0-9]+\\.[0-9]+(?:\\.[0-9]+)*") && info.path("participants").size()==10;
        for(var node:info.path("participants")) {
            String champion=node.path("championName").asString();
            champion=switch(champion) {case "FiddleSticks"->"Fiddlesticks";case "Wukong"->"MonkeyKing";default->champion;};
            String role=switch(node.path("teamPosition").asString()) {case "TOP"->"TOP";case "JUNGLE"->"JUNGLE";case "MIDDLE","MID"->"MID";case "BOTTOM","ADC","BOT"->"BOT";case "UTILITY","SUPPORT"->"SUPPORT";default->"";};
            int team=node.path("teamId").asInt();
            valid &= !champion.isBlank() && !role.isBlank() && (team==100 || team==200) && node.path("win").isBoolean() && !node.path("gameEndedInEarlySurrender").asBoolean(false);
            players.add(new Player(champion,role,team,node.path("win").asBoolean()));
        }
        for(int team:List.of(100,200)) {
            var side=players.stream().filter(p->p.team()==team).toList();
            valid &= side.size()==5 && side.stream().map(Player::role).distinct().count()==5 && side.stream().map(Player::champion).distinct().count()==5 && side.stream().map(Player::win).distinct().count()==1;
        }
        valid &= players.stream().map(Player::win).distinct().count()==2;
        var puuids=new ArrayList<String>();
        if(valid) for(var node:info.path("participants")) {
            String puuid=node.path("puuid").asString(); if(!puuid.isBlank()) puuids.add(puuid);
        }
        if(jdbc.update("insert into collection_matches(dataset_id,match_id,accepted,participant_puuids) values (?,?,?,?::jsonb) on conflict do nothing",dataset,id,valid,mapper.writeValueAsString(puuids))==0) return false;
        if(!valid) return false;
        String[] patchParts=version.split("\\."); String patch=patchParts[0]+"."+patchParts[1];
        for(var player:players) {
            increment("champion_role_stats",dataset,patch,queue,player,null,"");
            for(var other:players) {
                if(other==player) continue;
                if(player.team()==other.team()) increment("champion_synergy_stats",dataset,patch,queue,player,other,"");
                else if(player.role().equals(other.role())) increment("champion_matchup_stats",dataset,patch,queue,player,other,"");
            }
        }
        for(int team:List.of(100,200)) {
            var side=players.stream().filter(p->p.team()==team).toList();
            var flags=new TreeSet<String>(); boolean known=true;
            for(var player:side) {
                var rows=jdbc.queryForList("select raw_metadata::text from reference_champion_metadata where import_id=? and champion_id=?",String.class,metadataImport,player.champion());
                if(rows.isEmpty()) {known=false;break;}
                var metadata=mapper.readTree(rows.getFirst());
                if(!metadata.hasNonNull("utility_tags") || !metadata.hasNonNull("comp_tags") || !Set.of("AP","AD","Mixed","True").contains(metadata.path("damage_type").asString())) {known=false;break;}
                for(String field:List.of("utility_tags","comp_tags")) {
                    String tags=metadata.path(field).asString();
                    for(String tag:tags.replaceAll("[{}\\[\\]\"]","").split(",")) if(!tag.isBlank()) flags.add(field+":"+tag.strip());
                }
                String damage=metadata.path("damage_type").asString();
                if(damage.equals("AP") || damage.equals("Mixed") || damage.equals("True")) flags.add("damage:AP");
                if(damage.equals("AD") || damage.equals("Mixed") || damage.equals("True")) flags.add("damage:AD");
            }
            // Unknown traits are not silently classified as 'no frontline/no damage'.
            if(known) increment("team_comp_signature_stats",dataset,patch,queue,new Player("","",team,side.getFirst().win()),null,"traits-v1:"+(flags.isEmpty()?"none":String.join("|",flags)));
        }
        return true;
    }
    private void increment(String table,String dataset,String patch,int queue,Player p,Player other,String signature) {
        if(!TABLES.contains(table)) throw new IllegalArgumentException("Unknown statistics table");
        jdbc.update("insert into "+table+" (dataset_id,patch,queue_id,champion_id,role,partner_id,partner_role,signature,games,wins) values (?,?,?,?,?,?,?,?,1,?) on conflict(dataset_id,patch,queue_id,champion_id,role,partner_id,partner_role,signature) do update set games="+table+".games+1,wins="+table+".wins+excluded.wins",
            dataset,patch,queue,p.champion(),p.role(),other==null?"":other.champion(),other==null?"":other.role(),signature,p.win()?1:0);
    }
}
