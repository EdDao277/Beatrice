package com.beatrice.backend.collection;

import com.beatrice.backend.TestDatabase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest @Import(TestDatabase.class) @Transactional
class CollectionTest {
    @Autowired CollectionStats stats;
    @Autowired JdbcTemplate jdbc;
    @Autowired ObjectMapper mapper;
    @Test void discoveryReplaysFromAnAlreadyCommittedMatchWithoutDownloadingIt() {
        long archive=jdbc.queryForObject("insert into reference_imports(sha256,filename) values ('discovery-fixture','fixture') returning id",Long.class);
        jdbc.update("insert into reference_champion_metadata values (?, 'C0', '[]'::jsonb, '{}'::jsonb)",archive);
        var showMatch=new java.util.concurrent.atomic.AtomicBoolean(false);
        var fake=new com.beatrice.backend.riot.RiotClient("",mapper) {
            @Override public tools.jackson.databind.JsonNode get(boolean regional,String path) {
                if(path.contains("accounts/by-riot-id")) return mapper.readTree("{\"puuid\":\"seed\"}");
                if(path.contains("/ids?")) return mapper.readTree(showMatch.get()?"[\"NA1_saved\"]":"[]");
                throw new AssertionError("Already committed match must not be fetched");
            }
        };
        var collector=new CollectionCollector(jdbc,mapper,fake,stats);
        var config=new CollectionConfig("na1","americas",java.util.List.of("Seed#NA1"),java.util.List.of(400),1,1,3,"2026-07-29T19:00:00Z");
        collector.run(config);
        String dataset=jdbc.queryForObject("select id from collection_datasets",String.class);
        jdbc.update("insert into collection_matches values (?, 'NA1_saved', true, '[\"seed\",\"discovered\"]'::jsonb)",dataset);
        jdbc.update("update collection_cursors set done=false,position=0 where dataset_id=?",dataset);
        showMatch.set(true);
        assertEquals(0,collector.run(config).downloaded());
        assertEquals(1,jdbc.queryForObject("select depth from collection_players where dataset_id=? and puuid='discovered'",Integer.class,dataset));
    }
    @Test void collectorUsesFixturesAndResumesAtItsDownloadBudget() {
        long archive=jdbc.queryForObject("insert into reference_imports(sha256,filename) values ('crawler-fixture','fixture') returning id",Long.class);
        jdbc.update("insert into reference_champion_metadata values (?, 'C0', '[]'::jsonb, '{}'::jsonb)",archive);
        var fake=new com.beatrice.backend.riot.RiotClient("",mapper) {
            @Override public tools.jackson.databind.JsonNode get(boolean regional,String path) {
                if(path.contains("accounts/by-riot-id")) return mapper.readTree("{\"puuid\":\"seed\"}");
                if(path.contains("/ids?")) {
                    if(path.contains("start=0&")) return mapper.readTree("[\"NA1_one\",\"NA1_two\"]");
                    if(path.contains("start=1&")) return mapper.readTree("[\"NA1_two\"]");
                    return mapper.readTree("[]");
                }
                // Deliberately invalid game: ledger should remember rejection, not retry forever.
                return mapper.readTree("{\"metadata\":{\"matchId\":\""+(path.endsWith("NA1_one")?"NA1_one":"NA1_two")+"\"},\"info\":{\"participants\":[]}}");
            }
        };
        var collector=new CollectionCollector(jdbc,mapper,fake,stats);
        var config=new CollectionConfig("na1","americas",java.util.List.of("Seed#NA1"),java.util.List.of(400),1,0,1,"2026-07-29T19:00:00Z");
        assertEquals(1,collector.run(config).downloaded());
        assertEquals(1,collector.run(config).downloaded());
        assertEquals(0,collector.run(config).downloaded());
        assertEquals(2,jdbc.queryForObject("select count(*) from collection_matches",Integer.class));
    }
    @Test void oneMatchCreatesRoleSynergyCountersAndCompositionsOnlyOnce() {
        long archive=jdbc.queryForObject("insert into reference_imports(sha256,filename) values ('fixture-collection','fixture') returning id",Long.class);
        for(int i=0;i<10;i++) jdbc.update("insert into reference_champion_metadata values (?,?,'[]'::jsonb,?::jsonb)",archive,"C"+i,"{\"damage_type\":\"AD\",\"utility_tags\":\"{Frontline}\",\"comp_tags\":\"{Scaling}\"}");
        jdbc.update("insert into collection_datasets(id,split_start,metadata_import_id) values ('fixture',1,?)",archive);
        var match=mapper.createObjectNode();
        var info=match.putObject("info"); info.put("gameVersion","16.17.1.123"); info.put("queueId",400); info.put("gameStartTimestamp",2000);
        var players=info.putArray("participants");
        String[] roles={"TOP","JUNGLE","MIDDLE","BOTTOM","UTILITY"};
        for(int i=0;i<10;i++) { var p=players.addObject(); p.put("championName","C"+i); p.put("teamId",i<5?100:200); p.put("teamPosition",roles[i%5]); p.put("win",i<5); p.put("puuid","p"+i); }
        assertTrue(stats.accept("fixture","NA1_fixture",match,1,10,java.util.List.of(400),archive));
        assertFalse(stats.accept("fixture","NA1_fixture",match,1,10,java.util.List.of(400),archive));
        assertEquals(10,jdbc.queryForObject("select count(*) from champion_role_stats where dataset_id='fixture'",Integer.class));
        assertEquals(40,jdbc.queryForObject("select count(*) from champion_synergy_stats where dataset_id='fixture'",Integer.class));
        assertEquals(10,jdbc.queryForObject("select count(*) from champion_matchup_stats where dataset_id='fixture'",Integer.class));
        assertEquals(2,jdbc.queryForObject("select sum(games) from team_comp_signature_stats where dataset_id='fixture'",Integer.class));
        assertEquals(10,jdbc.queryForObject("select sum(games) from champion_role_stats where dataset_id='fixture'",Integer.class));
        assertEquals(10,jdbc.queryForObject("select count(*) from reference_champion_metadata where import_id=?",Integer.class,archive));
    }
    @Test void configurationRejectsUnsupportedQueues() {
        assertThrows(IllegalArgumentException.class,()->new CollectionConfig("na1","americas",java.util.List.of("A#NA1"),java.util.List.of(450),100,1,100,null).validate());
    }
}
