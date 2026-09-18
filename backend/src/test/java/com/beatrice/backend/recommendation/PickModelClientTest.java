package com.beatrice.backend.recommendation;

import java.time.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;

class PickModelClientTest {
    private final ObjectMapper mapper=new ObjectMapper();
    private final Instant now=Instant.parse("2026-09-14T12:00:00Z");
    private String response() {
        return """
          {"requestId":"r","schemaVersion":"beatrice-pick-recency-108-v1","modelVersion":"recency-2026-09-14",
          "modelSha256":"ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5",
          "historyBundleVersion":"refreshed-2026.09.17","historyBundleSha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          "historySnapshotId":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          "patch":"16.17","evidenceCutoff":"2026-09-13T00:00:00Z","historyLatest":"2026-09-10T00:00:00Z",
          "scores":[{"championId":"A","score":1.1,"globalGames":40,"recent30Picks":5,"patchGames":30,"seenInTrainingHistory":true}]}
          """;
    }
    private String freshResponse() {
        Instant cutoff=Instant.now().atOffset(ZoneOffset.UTC).toLocalDate().minusDays(1)
            .atStartOfDay().toInstant(ZoneOffset.UTC);
        return response().replace("2026-09-13T00:00:00Z",cutoff.toString())
            .replace("2026-09-10T00:00:00Z",cutoff.minus(Duration.ofDays(1)).toString());
    }
    @Test void validatesContractAndRejectsMismatchStaleFractionalOrOutsideResponse() {
        assertEquals(1,PickModelClient.validate(mapper.readTree(response()),"r","16.17",Set.of("A"),now).signals().size());
        for(String bad:List.of(response().replace("108-v1","108-v2"),response().replace("recency-2026-09-14","wrong"),
                response().replace("ea447","aaaaa"),response().replace("\"championId\":\"A\"","\"championId\":\"OUTSIDE\""),
                response().replace("2026-09-10","2026-09-01"),response().replace("2026-09-13","2026-09-15"),
                response().replace("\"globalGames\":40","\"globalGames\":40.5"),response().replace("\"score\":1.1","\"score\":null"))) {
            assertThrows(IllegalArgumentException.class,()->PickModelClient.validate(mapper.readTree(bad),"r","16.17",Set.of("A"),now));
        }
    }
    @Test void validProvenanceIsPreservedInResult() throws Exception {
        var server=server(freshResponse());
        try {
            var client=new PickModelClient(server.getAddress().getPort(),mapper);
            client.rank("r","16.17",List.of(),List.of(),List.of("A")); // Warm the strictly time-bounded HTTP client.
            var result=client.rank("r","16.17",List.of(),List.of(),List.of("A"));
            assertEquals("VALID",result.status());
            assertEquals("refreshed-2026.09.17",result.historyBundleVersion());
            assertEquals("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",result.historyBundleSha256());
            assertEquals("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",result.historySnapshotId());
        } finally {server.stop(0);}
    }
    @Test void malformedProvenanceRejectsWholeResponseBeforeSignals() throws Exception {
        String malformed=response().replace("refreshed-2026.09.17","refreshed/2026")
            .replace("\"score\":1.1","\"score\":null");
        var server=server(malformed);
        try {
            var result=new PickModelClient(server.getAddress().getPort(),mapper).rank("r","16.17",List.of(),List.of(),List.of("A"));
            assertNull(result.signals());
            assertEquals("INVALID_PROVENANCE",result.status());
            assertNull(result.historyBundleVersion());
            assertNull(result.historyBundleSha256());
            assertNull(result.historySnapshotId());
        } finally {server.stop(0);}
    }
    @Test void rejectsMissingOrMalformedHistoryProvenance() {
        String longVersion="a".repeat(101);
        for(String bad:List.of(
                response().replace("\"historyBundleVersion\":\"refreshed-2026.09.17\",", ""),
                response().replace("refreshed-2026.09.17",""),
                response().replace("refreshed-2026.09.17",longVersion),
                response().replace("refreshed-2026.09.17","unsafe/version"),
                response().replace("a".repeat(64),"A"+"a".repeat(63)),
                response().replace("b".repeat(64),"b".repeat(63)))) {
            var error=assertThrows(IllegalArgumentException.class,
                ()->PickModelClient.validate(mapper.readTree(bad),"r","16.17",Set.of("A"),now));
            assertEquals("INVALID_PROVENANCE",error.getMessage());
        }
    }
    @Test void unavailableLoopbackServiceReturnsSafeFailure() throws Exception {
        int port;
        try(var socket=new java.net.ServerSocket(0,0,java.net.InetAddress.getByName("127.0.0.1"))) {port=socket.getLocalPort();}
        var client=new PickModelClient(port,mapper);
        var result=client.rank("r","16.17",List.of(),List.of(),List.of("A"));
        assertNull(result.signals());
        assertEquals("ML_UNAVAILABLE",result.status());
    }
    @Test void delayedServiceTimesOutWithoutLeakingResponse() throws Exception {
        var server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/rank",exchange->{
            try {Thread.sleep(500);exchange.sendResponseHeaders(200,0);exchange.close();}
            catch(Exception ignored) {exchange.close();}
        });
        server.start();
        try {
            var client=new PickModelClient(server.getAddress().getPort(),mapper);
            client.rank("warmup","16.17",List.of(),List.of(),List.of("A"));
            long start=System.nanoTime();
            var result=client.rank("r","16.17",List.of(),List.of(),List.of("A"));
            assertNull(result.signals());assertEquals("ML_UNAVAILABLE",result.status());
            assertTrue((System.nanoTime()-start)/1e6<450,"Must not wait for delayed inference");
        } finally {server.stop(0);}
    }
    private static com.sun.net.httpserver.HttpServer server(String body) throws Exception {
        var server=com.sun.net.httpserver.HttpServer.create(new java.net.InetSocketAddress("127.0.0.1",0),0);
        server.createContext("/rank",exchange->{
            byte[] bytes=body.getBytes(java.nio.charset.StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200,bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
        });
        server.start();
        return server;
    }
}
