package com.beatrice.backend.oracle;

import com.beatrice.backend.champion.ChampionCatalog;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.LocalDateTime;
import java.util.*;

/** Explicit, transactional import of locally prepared evidence; no champion metadata writes. */
@Service
public class OracleImporter {
    public record Report(long importId,int inserted,int existing,boolean alreadyImported) {}
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final ChampionCatalog catalog;
    public OracleImporter(JdbcTemplate jdbc,ObjectMapper mapper,ChampionCatalog catalog) {
        this.jdbc=jdbc;this.mapper=mapper;this.catalog=catalog;
    }
    private static String hash(byte[] bytes) throws Exception {
        return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
    }
    @Transactional(rollbackFor=Exception.class)
    public Report importBatch(Path folder) throws Exception {
        Path source=folder.resolve("games.jsonl"), manifest=folder.resolve("report.json");
        if(Files.size(source)>256L*1024*1024 || Files.size(manifest)>2L*1024*1024) throw new IllegalArgumentException("Prepared batch is too large.");
        // Hash exactly the bytes we parse, so a file change cannot race the hash check.
        byte[] bytes=Files.readAllBytes(source), reportBytes=Files.readAllBytes(manifest);
        var report=mapper.readTree(reportBytes);
        String sha=hash(bytes);
        if(report.path("version").asInt()!=1 || !sha.equals(report.path("gamesSha256").asString())) throw new IllegalArgumentException("Prepared file hash/version mismatch.");
        var sources=new HashSet<String>();
        for(var sourceRow:report.path("sources")) {
            String sourceHash=sourceRow.path("sha256").asString("");
            if(!sourceHash.matches("[a-f0-9]{64}")) throw new IllegalArgumentException("Invalid manifest source hash.");
            sources.add(sourceHash);
        }
        if(sources.isEmpty()) throw new IllegalArgumentException("Missing manifest provenance.");
        String batchHash=hash((sha+hash(reportBytes)).getBytes(StandardCharsets.UTF_8));
        jdbc.execute("select pg_advisory_xact_lock(70420260908)");
        var previous=jdbc.queryForList("select id from oracle_imports where sha256=?",Long.class,batchHash);
        if(!previous.isEmpty()) return new Report(previous.getFirst(),0,0,true);
        long importId=jdbc.queryForObject("insert into oracle_imports(sha256,report) values (?,?::jsonb) returning id",Long.class,batchHash,new String(reportBytes,StandardCharsets.UTF_8));
        int inserted=0,existing=0;
        var seen=new HashSet<String>();
        try(var reader=new java.io.BufferedReader(new java.io.StringReader(new String(bytes,StandardCharsets.UTF_8)))) {
            String line;
            while((line=reader.readLine())!=null) {
                if(line.isBlank()) throw new IllegalArgumentException("Empty prepared record.");
                var envelope=mapper.readTree(line);var game=envelope.path("game");
                validate(game);
                String id=game.path("gameId").asString();
                if(!seen.add(id)) throw new IllegalArgumentException("Duplicate prepared game: "+id);
                String payload=mapper.writeValueAsString(game), gameHash=hash(payload.getBytes(StandardCharsets.UTF_8));
                var old=jdbc.queryForList("select sha256 from oracle_matches where game_id=?",String.class,id);
                if(!old.isEmpty()) {
                    if(!old.getFirst().equals(gameHash)) throw new IllegalArgumentException("Conflicting game: "+id+". Existing data was not overwritten.");
                    existing++;
                } else {
                    jdbc.update("insert into oracle_matches(game_id,played_at,patch,league,draft_fields_complete,sha256,payload) values (?,?,?,?,?,?,?::jsonb)",
                        id,LocalDateTime.parse(game.path("date").asString().replace(' ','T')),game.path("patch").asString(),game.path("league").asString(),game.path("draftFieldsComplete").asBoolean(),gameHash,payload);
                    inserted++;
                }
                if(!envelope.path("sources").isArray() || envelope.path("sources").isEmpty()) throw new IllegalArgumentException("Missing source provenance.");
                for(var provenance:envelope.path("sources")) if(!sources.contains(provenance.asString(""))) throw new IllegalArgumentException("Unknown source provenance.");
                jdbc.update("insert into oracle_match_sources(import_id,game_id,source_hashes) values (?,?,?::jsonb)",importId,id,mapper.writeValueAsString(envelope.path("sources")));
            }
        }
        if(seen.size()!=report.path("acceptedGames").asInt(-1) || seen.isEmpty()) throw new IllegalArgumentException("Prepared record count mismatch or empty batch.");
        return new Report(importId,inserted,existing,false);
    }
    private void validate(JsonNode game) {
        if(game.path("gameId").asString("").isBlank() || !game.path("patch").asString("").matches("[0-9]{1,3}\\.[0-9]{1,3}")
            || game.path("league").asString("").isBlank() || game.path("teams").size()!=2) throw new IllegalArgumentException("Invalid prepared game.");
        var champions=new HashSet<String>();var sides=new HashSet<String>();int wins=0;
        var bans=new HashSet<String>();boolean complete=true;
        for(var team:game.path("teams")) {
            String side=team.path("side").asString("");
            if(!Set.of("BLUE","RED").contains(side) || !sides.add(side)) throw new IllegalArgumentException("Invalid sides.");
            int result=team.path("result").asInt(-1);
            if(result!=0 && result!=1) throw new IllegalArgumentException("Invalid result.");wins+=result;
            var roles=new HashSet<String>();var ownChampions=new HashSet<String>();
            for(var player:team.path("players")) {
                String id=player.path("championId").asString("");catalog.require(id);
                ownChampions.add(id);
                if(!champions.add(id) || !roles.add(player.path("role").asString(""))) throw new IllegalArgumentException("Duplicate champion/role.");
            }
            if(!roles.equals(Set.of("TOP","JUNGLE","MID","BOT","SUPPORT"))) throw new IllegalArgumentException("Invalid final roles.");
            for(String field:List.of("picks","bans")) {
                if(!team.path(field).isArray() || team.path(field).size()!=5) throw new IllegalArgumentException("Invalid draft fields.");
                for(var id:team.path(field)) if(!id.isNull()) catalog.require(id.asString());
            }
            var picks=new HashSet<String>();
            for(var id:team.path("picks")) {if(id.isNull()) complete=false;else picks.add(id.asString());}
            complete &= picks.equals(ownChampions);
            for(var id:team.path("bans")) {if(id.isNull()) complete=false;else if(!bans.add(id.asString())) complete=false;}
        }
        if(wins!=1) throw new IllegalArgumentException("Invalid opposing results.");
        complete &= Collections.disjoint(bans,champions);
        if(!game.path("draftFieldsComplete").isBoolean() || complete!=game.path("draftFieldsComplete").asBoolean()) throw new IllegalArgumentException("Incorrect draft completeness flag.");
    }
}
