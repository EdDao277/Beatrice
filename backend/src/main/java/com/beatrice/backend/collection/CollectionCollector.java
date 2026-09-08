package com.beatrice.backend.collection;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.*;
import com.beatrice.backend.riot.RiotClient;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import tools.jackson.databind.ObjectMapper;

@Service
public class CollectionCollector {
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final RiotClient riot;
    private final CollectionStats stats;
    public record Report(long runId,int downloaded,int accepted,String status) {}
    public CollectionCollector(JdbcTemplate jdbc,ObjectMapper mapper,RiotClient riot,CollectionStats stats) {
        this.jdbc=jdbc;this.mapper=mapper;this.riot=riot;this.stats=stats;
    }
    public synchronized Report run(CollectionConfig config) {
        config.validate();
        // Session lock protects against a second JVM, not just duplicate HTTP requests.
        try(var lock=Objects.requireNonNull(jdbc.getDataSource()).getConnection();var statement=lock.createStatement()) {
            try(var result=statement.executeQuery("select pg_try_advisory_lock(70420260907)")) {
                result.next(); if(!result.getBoolean(1)) throw new IllegalStateException("Another collection is already running.");
            }
            try { return collect(config); }
            finally { statement.execute("select pg_advisory_unlock(70420260907)"); }
        } catch(java.sql.SQLException e) {throw new IllegalStateException("Collection database unavailable.");}
    }
    private Report collect(CollectionConfig config) {
        var imports=jdbc.queryForList("select distinct import_id from reference_champion_metadata order by import_id desc limit 1",Long.class);
        if(imports.isEmpty()) throw new IllegalStateException("Import champion metadata before collecting; metadata will not be changed.");
        long archive=imports.getFirst(),start=config.start(),end=Instant.now().getEpochSecond();
        String dataset;
        try {
            String identity=config.region()+"|"+config.platform()+"|"+start+"|"+archive+"|"+config.queues().stream().sorted().toList()+"|"+config.seedRiotIds().stream().map(s->s.strip().toLowerCase(Locale.ROOT)).sorted().toList();
            dataset=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(identity.getBytes(StandardCharsets.UTF_8)));
        } catch(Exception e) {throw new IllegalStateException("Cannot identify collection.");}
        jdbc.update("insert into collection_datasets values (?,?,?) on conflict do nothing",dataset,start,archive);
        long run=jdbc.queryForObject("insert into collection_runs(dataset_id) values (?) returning id",Long.class,dataset);
        int downloaded=0,accepted=0;
        try {
            for(String seed:config.seedRiotIds()) {
                // Resolve seeds on each run to tolerate renamed accounts; discovered players already have PUUIDs.
                String[] parts=seed.strip().split("#",2);
                var account=riot.get(true,"/riot/account/v1/accounts/by-riot-id/"+RiotClient.segment(parts[0])+"/"+RiotClient.segment(parts[1]));
                String puuid=account.path("puuid").asString();
                if(puuid.isBlank()) throw new IllegalStateException("Seed account missing PUUID.");
                jdbc.update("insert into collection_players values (?,?,0) on conflict(dataset_id,puuid) do update set depth=0",dataset,puuid);
            }
            var visited=new HashSet<String>();
            // Limits also bound empty-history requests; no uncontrolled graph expansion.
            while(downloaded<config.maxNewMatchesPerRun()) {
                var players=jdbc.queryForList("select puuid,depth from collection_players where dataset_id=? and depth<=? order by depth,puuid",dataset,config.maxDiscoveryDepth());
                boolean worked=false;
                for(var player:players) {
                    String puuid=(String)player.get("puuid"); int depth=((Number)player.get("depth")).intValue();
                    if(!visited.add(puuid)) continue;
                    worked=true;
                    for(int queue:config.queues()) {
                        jdbc.update("insert into collection_cursors(dataset_id,puuid,queue_id,window_start,window_end) values (?,?,?,?,?) on conflict do nothing",dataset,puuid,queue,start,end);
                        var cursor=jdbc.queryForMap("select * from collection_cursors where dataset_id=? and puuid=? and queue_id=?",dataset,puuid,queue);
                        long from=((Number)cursor.get("window_start")).longValue(),through=((Number)cursor.get("window_end")).longValue();
                        int position=((Number)cursor.get("position")).intValue();
                        if((Boolean)cursor.get("done")) {
                            if(end-through<60) continue;
                            from=Math.max(start,through-86400); through=end;position=0;
                            jdbc.update("update collection_cursors set window_start=?,window_end=?,position=0,done=false where dataset_id=? and puuid=? and queue_id=?",from,through,dataset,puuid,queue);
                        }
                        while(downloaded<config.maxNewMatchesPerRun()) {
                            var ids=riot.get(true,"/lol/match/v5/matches/by-puuid/"+RiotClient.segment(puuid)+"/ids?start="+position+"&count=100&queue="+queue+"&startTime="+from+"&endTime="+through);
                            if(!ids.isArray()) throw new IllegalStateException("Invalid match history response.");
                            int processed=0;
                            for(var value:ids) {
                                if(downloaded>=config.maxNewMatchesPerRun()) break;
                                String id=value.asString();
                                if(!id.matches("NA1_[A-Za-z0-9]+")) throw new IllegalStateException("Unexpected match identifier.");
                                if(jdbc.queryForObject("select count(*) from collection_matches where dataset_id=? and match_id=?",Integer.class,dataset,id)==0) {
                                    var match=riot.get(true,"/lol/match/v5/matches/"+RiotClient.segment(id));
                                    downloaded++;
                                    if(!id.equals(match.path("metadata").path("matchId").asString())) throw new IllegalStateException("Mismatched match response.");
                                    boolean valid=stats.accept(dataset,id,match,start,end,config.queues(),archive);
                                    if(valid) accepted++;
                                    jdbc.update("update collection_runs set downloaded=?,accepted=? where id=?",downloaded,accepted,run);
                                }
                                // Discovery can be replayed from the ledger even after aggregate commit,
                                // and when a cached match is later reached at a shallower depth.
                                if(depth<config.maxDiscoveryDepth()) {
                                    var discovered=jdbc.queryForList("select participant_puuids::text from collection_matches where dataset_id=? and match_id=? and accepted",String.class,dataset,id);
                                    for(String json:discovered) for(var participant:mapper.readTree(json)) {
                                        String found=participant.asString();
                                        int updated=jdbc.update("update collection_players set depth=least(depth,?) where dataset_id=? and puuid=?",depth+1,dataset,found);
                                        int count=jdbc.queryForObject("select count(*) from collection_players where dataset_id=?",Integer.class,dataset);
                                        if(updated==0 && count<config.maxTrackedPlayers()) jdbc.update("insert into collection_players values (?,?,?) on conflict do nothing",dataset,found,depth+1);
                                    }
                                }
                                processed++;position++;
                                // A crash between aggregate commit and this checkpoint replays a deduplicated ID.
                                jdbc.update("update collection_cursors set position=? where dataset_id=? and puuid=? and queue_id=?",position,dataset,puuid,queue);
                            }
                            if(processed==ids.size() && ids.size()<100) {
                                jdbc.update("update collection_cursors set done=true where dataset_id=? and puuid=? and queue_id=?",dataset,puuid,queue); break;
                            }
                        }
                        if(downloaded>=config.maxNewMatchesPerRun()) break;
                    }
                    if(downloaded>=config.maxNewMatchesPerRun()) break;
                }
                if(!worked) break;
            }
            String status=downloaded>=config.maxNewMatchesPerRun()?"BUDGET_REACHED":"WINDOWS_CHECKED";
            jdbc.update("update collection_runs set status=?,finished_at=now(),downloaded=?,accepted=? where id=?",status,downloaded,accepted,run);
            return new Report(run,downloaded,accepted,status);
        } catch(RuntimeException e) {
            jdbc.update("update collection_runs set status='FAILED_RETRYABLE',finished_at=now(),downloaded=?,accepted=? where id=?",downloaded,accepted,run);
            throw e;
        }
    }
}
