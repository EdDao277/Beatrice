package com.beatrice.backend.recommendation;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.*;

/** Loopback only. Validate the entire envelope before allowing any candidate bonus. */
@Component
public final class PickModelClient {
    public static final String MODEL="recency-2026-09-14", SCHEMA="beatrice-pick-recency-108-v1";
    public static final String HASH="ea447cdced1aa541446c50ef03c2ed96f06ecd94e4f50fb50514f17d85964ec5";
    private static final Pattern BUNDLE_VERSION=Pattern.compile("[A-Za-z0-9._-]+");
    private static final Pattern SHA256=Pattern.compile("[0-9a-f]{64}");
    public record Result(List<GuardedPickBonus.Signal> signals,String status,double latencyMs,
        String historyBundleVersion,String historyBundleSha256,String historySnapshotId) {
        Result(List<GuardedPickBonus.Signal> signals,String status,double latencyMs) {
            this(signals,status,latencyMs,null,null,null);
        }
    }
    record Validated(List<GuardedPickBonus.Signal> signals,String historyBundleVersion,
        String historyBundleSha256,String historySnapshotId) {}
    private final URI uri;
    private final ObjectMapper mapper;
    private final HttpClient client=HttpClient.newBuilder().connectTimeout(Duration.ofMillis(100)).followRedirects(HttpClient.Redirect.NEVER).build();
    public PickModelClient(@Value("${beatrice.ml.port:8766}") int port,ObjectMapper mapper) {
        if(port<1 || port>65535) throw new IllegalArgumentException("Invalid local inference port");
        uri=URI.create("http://127.0.0.1:"+port+"/rank");this.mapper=mapper;
    }
    public Result rank(String requestId,String patch,List<String> allies,List<String> enemies,List<String> ids) {
        long start=System.nanoTime();CompletableFuture<HttpResponse<byte[]>> pending=null;
        try {
            var body=Map.of("requestId",requestId,"schemaVersion",SCHEMA,"modelVersion",MODEL,"modelSha256",HASH,
                "patch",patch,"allyPicks",allies,"enemyPicks",enemies,"candidateIds",ids);
            var request=HttpRequest.newBuilder(uri).timeout(Duration.ofMillis(100)).header("Content-Type","application/json")
                .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(body))).build();
            pending=client.sendAsync(request,info->new LimitedBody());
            var response=pending.get(100,TimeUnit.MILLISECONDS);
            if(response.statusCode()!=200) return failure("ML_UNAVAILABLE",start);
            var validated=validate(mapper.readTree(response.body()),requestId,patch,new HashSet<>(ids),Instant.now());
            return new Result(validated.signals(),"VALID",elapsed(start),validated.historyBundleVersion(),
                validated.historyBundleSha256(),validated.historySnapshotId());
        } catch(Rejected e) {return failure(e.getMessage(),start);}
        catch(InterruptedException e) {Thread.currentThread().interrupt();return failure("ML_UNAVAILABLE",start);}
        catch(Exception e) {return failure("ML_UNAVAILABLE",start);}
        finally {if(pending!=null && !pending.isDone()) pending.cancel(true);}
    }
    private static Result failure(String reason,long start) {return new Result(null,reason,elapsed(start));}
    private static double elapsed(long start) {return (System.nanoTime()-start)/1e6;}
    private static final class Rejected extends IllegalArgumentException {Rejected(String reason) {super(reason);}}
    private static void require(boolean condition,String reason) {if(!condition) throw new Rejected(reason);}
    static Validated validate(JsonNode node,String requestId,String patch,Set<String> ids,Instant now) {
        require(node!=null && node.isObject(),"INVALID_RESPONSE");
        require(SCHEMA.equals(node.path("schemaVersion").asString()) && MODEL.equals(node.path("modelVersion").asString())
            && HASH.equals(node.path("modelSha256").asString()),"MODEL_SCHEMA_MISMATCH");
        require(requestId.equals(node.path("requestId").asString()) && patch.equals(node.path("patch").asString()),"INVALID_RESPONSE");
        var version=node.path("historyBundleVersion");var bundleHash=node.path("historyBundleSha256");
        var snapshot=node.path("historySnapshotId");
        require(version.isTextual() && !version.asString().isBlank() && version.asString().length()<=100
            && BUNDLE_VERSION.matcher(version.asString()).matches()
            && bundleHash.isTextual() && SHA256.matcher(bundleHash.asString()).matches()
            && snapshot.isTextual() && SHA256.matcher(snapshot.asString()).matches(),"INVALID_PROVENANCE");
        Instant cutoff,latest;
        try {cutoff=Instant.parse(node.path("evidenceCutoff").asString());latest=Instant.parse(node.path("historyLatest").asString());}
        catch(Exception e) {throw new Rejected("INVALID_EVIDENCE_TIME");}
        var latestAllowed=now.atOffset(ZoneOffset.UTC).toLocalDate().minusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC);
        require(!cutoff.isAfter(latestAllowed) && latest.isBefore(cutoff),"INVALID_EVIDENCE_TIME");
        require(!latest.isBefore(now.minus(Duration.ofDays(7))),"STALE_EVIDENCE");
        var rows=node.path("scores");require(rows.isArray() && rows.size()==ids.size() && rows.size()<=200,"INVALID_RESPONSE");
        var seen=new HashSet<String>();var result=new ArrayList<GuardedPickBonus.Signal>();
        for(var row:rows) {
            String id=row.path("championId").asString();
            require(ids.contains(id) && seen.add(id) && row.path("score").isNumber()
                && Double.isFinite(row.path("score").asDouble()) && row.path("seenInTrainingHistory").isBoolean(),"INVALID_RESPONSE");
            long global=count(row,"globalGames"),recent=count(row,"recent30Picks"),patchGames=count(row,"patchGames");
            require(recent<=global,"INVALID_RESPONSE");
            result.add(new GuardedPickBonus.Signal(id,row.path("score").asDouble(),global,recent,patchGames,row.path("seenInTrainingHistory").asBoolean()));
        }
        require(seen.equals(ids),"INVALID_RESPONSE");
        return new Validated(List.copyOf(result),version.asString(),bundleHash.asString(),snapshot.asString());
    }
    private static long count(JsonNode node,String key) {
        var n=node.path(key);
        require(n.isIntegralNumber() && n.asDouble()>=0 && n.asDouble()<=9_007_199_254_740_991L,"INVALID_RESPONSE");
        return n.asLong();
    }
    /** Limit memory even if a broken local process streams an oversized response. */
    private static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {
        private final CompletableFuture<byte[]> body=new CompletableFuture<>();
        private final ByteArrayOutputStream bytes=new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        public CompletionStage<byte[]> getBody() {return body;}
        public void onSubscribe(Flow.Subscription value) {subscription=value;value.request(1);}
        public void onNext(List<ByteBuffer> buffers) {
            for(var buffer:buffers) {
                if(bytes.size()+buffer.remaining()>131072) {subscription.cancel();body.completeExceptionally(new IllegalArgumentException("Response too large"));return;}
                byte[] chunk=new byte[buffer.remaining()];buffer.get(chunk);bytes.writeBytes(chunk);
            }
            subscription.request(1);
        }
        public void onError(Throwable error) {body.completeExceptionally(error);}
        public void onComplete() {body.complete(bytes.toByteArray());}
    }
}
