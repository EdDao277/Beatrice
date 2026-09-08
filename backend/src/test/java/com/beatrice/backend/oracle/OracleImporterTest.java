package com.beatrice.backend.oracle;

import com.beatrice.backend.TestDatabase;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import java.nio.file.*;
import java.security.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest @Import(TestDatabase.class)
class OracleImporterTest {
    @Autowired OracleImporter importer;
    @Autowired JdbcTemplate jdbc;
    void rewrite(Path path,String content) throws Exception {
        Files.writeString(path.resolve("games.jsonl"),content);
        String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(path.resolve("games.jsonl"))));
        String report=Files.readString(path.resolve("report.json"));
        Files.writeString(path.resolve("report.json"),report.replaceAll("\"gamesSha256\":\"[a-f0-9]+\"","\"gamesSha256\":\""+sha+"\""));
    }
    Path batch(String id,String league) throws Exception {
        var path=Files.createTempDirectory("oracle-fixture-");
        var players=new ArrayList<String>();
        for(int i=0;i<10;i++) players.add("{\"role\":\""+List.of("TOP","JUNGLE","MID","BOT","SUPPORT").get(i%5)+"\",\"championId\":\"C"+i+"\"}");
        String game="{\"gameId\":\""+id+"\",\"date\":\"2026-01-01 10:00:00\",\"patch\":\"16.1\",\"league\":\""+league+"\",\"draftFieldsComplete\":false,\"teams\":[{\"side\":\"BLUE\",\"result\":1,\"players\":["+String.join(",",players.subList(0,5))+"],\"picks\":[null,null,null,null,null],\"bans\":[null,null,null,null,null]},{\"side\":\"RED\",\"result\":0,\"players\":["+String.join(",",players.subList(5,10))+"],\"picks\":[null,null,null,null,null],\"bans\":[null,null,null,null,null]}]}";
        byte[] bytes=("{\"game\":"+game+",\"sources\":[\""+"a".repeat(64)+"\"]}\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
        Files.write(path.resolve("games.jsonl"),bytes);
        String sha=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        Files.writeString(path.resolve("report.json"),"{\"version\":1,\"sources\":[{\"sha256\":\""+"a".repeat(64)+"\"}],\"acceptedGames\":1,\"gamesSha256\":\""+sha+"\"}");
        return path;
    }
    @Test void importsOnceAndRejectsConflictingBatchAtomically() throws Exception {
        String id="fixture-"+UUID.randomUUID();
        var first=batch(id,"Fixture");
        assertEquals(1,importer.importBatch(first).inserted());
        assertTrue(importer.importBatch(first).alreadyImported());
        long count=jdbc.queryForObject("select count(*) from oracle_imports",Long.class);
        assertThrows(Exception.class,()->importer.importBatch(batch(id,"Changed")));
        assertEquals(count,jdbc.queryForObject("select count(*) from oracle_imports",Long.class));
        assertEquals("Fixture",jdbc.queryForObject("select league from oracle_matches where game_id=?",String.class,id));
    }
    @Test void rejectsTamperedPreparedFile() throws Exception {
        var path=batch("bad-"+UUID.randomUUID(),"Fixture");
        Files.writeString(path.resolve("games.jsonl"),"{}\n",StandardOpenOption.APPEND);
        assertThrows(Exception.class,()->importer.importBatch(path));
    }
    @Test void rejectsFalseCompletenessAndUnknownProvenance() throws Exception {
        var path=batch("invalid-"+UUID.randomUUID(),"Fixture");
        String original=Files.readString(path.resolve("games.jsonl"));
        rewrite(path,original.replace("\"draftFieldsComplete\":false","\"draftFieldsComplete\":true"));
        assertThrows(IllegalArgumentException.class,()->importer.importBatch(path));
        rewrite(path,original.replace("a".repeat(64),"b".repeat(64)));
        assertThrows(IllegalArgumentException.class,()->importer.importBatch(path));
    }
    @Test void preservesNewManifestAndRollsBackEarlierRowsOnConflict() throws Exception {
        String id="existing-"+UUID.randomUUID(), freshId="fresh-"+UUID.randomUUID();
        var first=batch(id,"Fixture");importer.importBatch(first);
        Files.writeString(first.resolve("report.json"),Files.readString(first.resolve("report.json")).replace("\"version\":1","\"auditNote\":\"new audit\",\"version\":1"));
        var next=importer.importBatch(first);
        assertFalse(next.alreadyImported());assertEquals(1,next.existing());
        var conflicting=batch(id,"Changed");var fresh=batch(freshId,"Fixture");
        rewrite(conflicting,Files.readString(fresh.resolve("games.jsonl"))+Files.readString(conflicting.resolve("games.jsonl")));
        Files.writeString(conflicting.resolve("report.json"),Files.readString(conflicting.resolve("report.json")).replace("\"acceptedGames\":1","\"acceptedGames\":2"));
        long imports=jdbc.queryForObject("select count(*) from oracle_imports",Long.class);
        assertThrows(IllegalArgumentException.class,()->importer.importBatch(conflicting));
        assertEquals(0,jdbc.queryForObject("select count(*) from oracle_matches where game_id=?",Integer.class,freshId));
        assertEquals(imports,jdbc.queryForObject("select count(*) from oracle_imports",Long.class));
    }
}
