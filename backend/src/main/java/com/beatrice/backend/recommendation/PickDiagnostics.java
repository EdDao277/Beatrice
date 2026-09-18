package com.beatrice.backend.recommendation;

import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/** Bounded local diagnostics. No player identities, credentials, or database writes. */
@Component
public final class PickDiagnostics {
    private record Receipt(long teamId,Set<String> candidates,Instant at) {}
    private final LinkedHashMap<String,Receipt> receipts=new LinkedHashMap<>();
    private final Path folder;private final ObjectMapper mapper;
    public PickDiagnostics(@Value("${beatrice.ml.log-path:../data/diagnostics/picks}") String folder,ObjectMapper mapper) {
        this.folder=Path.of(folder);this.mapper=mapper;
    }
    public synchronized void record(String requestId,long teamId,List<GuardedPickBonus.Base> bases,GuardedPickBonus.Result result,double latencyMs) {
        record(requestId,teamId,bases,result,latencyMs,null,null,null);
    }
    public synchronized void record(String requestId,long teamId,List<GuardedPickBonus.Base> bases,GuardedPickBonus.Result result,
            PickModelClient.Result inference) {
        record(requestId,teamId,bases,result,inference.latencyMs(),inference.historyBundleVersion(),
            inference.historyBundleSha256(),inference.historySnapshotId());
    }
    private void record(String requestId,long teamId,List<GuardedPickBonus.Base> bases,GuardedPickBonus.Result result,double latencyMs,
            String historyBundleVersion,String historyBundleSha256,String historySnapshotId) {
        prune();
        if(receipts.size()>=256) receipts.remove(receipts.keySet().iterator().next());
        receipts.put(requestId,new Receipt(teamId,new HashSet<>(bases.stream().map(GuardedPickBonus.Base::championId).toList()),Instant.now()));
        var event=new LinkedHashMap<String,Object>();
        event.put("event","recommendation");event.put("at",Instant.now().toString());event.put("requestId",requestId);event.put("teamId",teamId);
        event.put("javaRanking",bases);event.put("mlRanking",result.mlRanking());event.put("finalRanking",result.picks());
        event.put("gateResult",result.status());event.put("modelVersion",PickModelClient.MODEL);event.put("inferenceLatencyMs",latencyMs);
        event.put("historyBundleVersion",historyBundleVersion);event.put("historyBundleSha256",historyBundleSha256);
        event.put("historySnapshotId",historySnapshotId);
        append(event);
    }
    public synchronized boolean selected(String requestId,long teamId,String championId) {
        prune();var receipt=receipts.get(requestId);
        if(receipt==null || receipt.teamId()!=teamId || !receipt.candidates().contains(championId)) return false;
        receipts.remove(requestId);
        append(Map.of("event","selection","at",Instant.now().toString(),"requestId",requestId,"teamId",teamId,"selectedChampionId",championId));
        return true;
    }
    private void prune() {var cutoff=Instant.now().minus(Duration.ofMinutes(30));receipts.values().removeIf(r->r.at().isBefore(cutoff));}
    private void append(Object event) {
        try {
            Files.createDirectories(folder);var file=folder.resolve("picks.jsonl");
            if(Files.exists(file) && Files.size(file)>=2_000_000) {
                var old=folder.resolve("picks.1.jsonl");
                if(Files.exists(old)) Files.move(old,folder.resolve("picks.2.jsonl"),StandardCopyOption.REPLACE_EXISTING);
                Files.move(file,old,StandardCopyOption.REPLACE_EXISTING);
            }
            Files.writeString(file,mapper.writeValueAsString(event)+System.lineSeparator(),StandardOpenOption.CREATE,StandardOpenOption.APPEND);
        } catch(Exception ignored) {
            // Diagnostics are best-effort; a full/unwritable disk must never break the draft.
        }
    }
}
