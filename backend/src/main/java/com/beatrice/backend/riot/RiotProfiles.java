package com.beatrice.backend.riot;

import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;
import jakarta.annotation.PreDestroy;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.*;
import com.beatrice.backend.team.TeamService;
import com.beatrice.backend.team.TeamData.Role;
import com.beatrice.backend.champion.ChampionCatalog;
import static org.springframework.http.HttpStatus.*;

@Service
public class RiotProfiles {
    public record Rank(String tier, String division, int lp, int wins, int losses) {}
    public record Snapshot(String riotId, String iconUrl, Rank rank, RiotStats.Sample sample, int requestedMatches, Instant updatedAt,
        List<Integer> queues, Integer scannedMatches, Boolean historyScanLimited,
        RiotRanks.Rank highestRank, List<RiotMastery.Champion> mastery, Instant splitStart, Boolean splitComplete, Integer splitWins) {}
    public record State(Snapshot profile, boolean refreshing, String message) {}
    private record Progress(boolean refreshing, String message, long attemptedAt) {}
    private final Map<String,Progress> jobs = new ConcurrentHashMap<>();
    private final ThreadPoolExecutor worker = new ThreadPoolExecutor(1,1,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(10),
        task -> { var thread = new Thread(task,"riot-refresh"); thread.setDaemon(true); return thread; });
    private final RiotClient riot;
    private final JdbcTemplate jdbc;
    private final ObjectMapper mapper;
    private final TeamService teams;
    private final ChampionCatalog catalog;
    private final RiotSplitHistory splitHistory;
    private final Instant splitStart;
    public RiotProfiles(RiotClient riot, JdbcTemplate jdbc, ObjectMapper mapper, TeamService teams, ChampionCatalog catalog,
        RiotSplitHistory splitHistory, @Value("${beatrice.riot.split-start:2026-07-29T19:00:00Z}") String splitStart) {
        this.riot=riot; this.jdbc=jdbc; this.mapper=mapper; this.teams=teams; this.catalog=catalog;
        this.splitHistory=splitHistory; this.splitStart=Instant.parse(splitStart);
    }
    @PreDestroy void stop() { worker.shutdownNow(); }
    private String savedId(long teamId, Role role) {
        return teams.get(teamId).players().stream().filter(p -> p.role()==role).findFirst().orElseThrow().riotId().strip();
    }
    private String cacheKey(String id) { return "na1:" + id.toLowerCase(Locale.ROOT); }
    public State get(long teamId, Role role) { return state(cacheKey(savedId(teamId,role))); }
    private State state(String key) {
        var progress = jobs.get(key);
        // Worker commits the snapshot before setting refreshing=false. Read progress first
        // so a completion racing this GET cannot stop polling with an older snapshot.
        var snapshots = jdbc.queryForList("select snapshot::text from riot_profile_cache where riot_id=?",String.class,key);
        return new State(snapshots.isEmpty() ? null : mapper.readValue(snapshots.getFirst(),Snapshot.class),
            progress != null && progress.refreshing(), progress == null ? "" : progress.message());
    }
    public synchronized State refresh(long teamId, Role role) {
        String id = savedId(teamId,role);
        if (!id.matches("[^#]+#[^#]+")) throw new ResponseStatusException(BAD_REQUEST,"Save a full Name#Tag on the Team page first.");
        String key = cacheKey(id);
        var previous = jobs.get(key);
        if (previous != null && previous.refreshing()) return state(key);
        if (previous != null && System.currentTimeMillis()-previous.attemptedAt()<60000)
            throw new ResponseStatusException(TOO_MANY_REQUESTS,"Wait one minute between refresh attempts.");
        long started = System.currentTimeMillis();
        jobs.put(key,new Progress(true,"Queued for Riot refresh…",started));
        try { worker.execute(() -> {
            try {
                var snapshot = fetch(id,key,started);
                jdbc.update("insert into riot_profile_cache(riot_id,snapshot) values (?,?::jsonb) on conflict(riot_id) do update set snapshot=excluded.snapshot",
                    key,mapper.writeValueAsString(snapshot));
                jobs.put(key,new Progress(false,"",started));
            } catch (Exception error) {
                String message = error instanceof ResponseStatusException status ? status.getReason() : "Refresh failed. Previous stats are preserved. Please retry.";
                jobs.put(key,new Progress(false,message,started));
            }
        }); } catch (RejectedExecutionException error) {
            jobs.remove(key);
            throw new ResponseStatusException(TOO_MANY_REQUESTS,"Refresh queue is full. Try again shortly.");
        }
        return state(key);
    }
    private Snapshot fetch(String id,String key,long started) {
        String[] parts = id.split("#",2);
        var account = riot.get(true,"/riot/account/v1/accounts/by-riot-id/"+RiotClient.segment(parts[0])+"/"+RiotClient.segment(parts[1]));
        String puuid = account.path("puuid").asString();
        if (puuid.isBlank()) throw new IllegalStateException("Missing account identifier");
        String encoded = RiotClient.segment(puuid);
        var summoner = riot.get(false,"/lol/summoner/v4/summoners/by-puuid/"+encoded);
        var leagues = riot.get(false,"/lol/league/v4/entries/by-puuid/"+encoded);
        if (!leagues.isArray()) throw new IllegalStateException("Invalid ranked response");
        Rank rank = null;
        for (var league : leagues) if (league.path("queueType").asString().equals("RANKED_SOLO_5x5"))
            rank = new Rank(league.path("tier").asString(),league.path("rank").asString(),league.path("leaguePoints").asInt(),league.path("wins").asInt(),league.path("losses").asInt());
        var highest = RiotRanks.highest(leagues);
        var mastery = RiotMastery.top(riot.get(false,"/lol/champion-mastery/v4/champion-masteries/by-puuid/"+encoded+"/top?count=3"),catalog::idForKey);
        Instant through = Instant.now();
        if (!splitStart.isBefore(through)) throw new IllegalStateException("Split start must be in the past");
        var history = splitHistory.sync(puuid,splitStart,through,path -> riot.get(true,path),downloaded ->
            jobs.put(key,new Progress(true,"Split sync in progress · "+downloaded+" new matches cached…",started)));
        String patch = catalog.catalog().version();
        if (!patch.matches("[0-9]+\\.[0-9]+\\.[0-9]+")) throw new IllegalStateException("Invalid asset patch");
        String icon = "https://ddragon.leagueoflegends.com/cdn/"+patch+"/img/profileicon/"+summoner.path("profileIconId").asInt()+".png";
        var sample = history.sample();
        var named = sample.champions().stream().map(c -> new RiotStats.Champion(c.id(),
            catalog.catalog().champions().stream().filter(entry -> entry.id().equals(c.id())).map(ChampionCatalog.Champion::name).findFirst().orElse(c.id()),
            c.games(),c.wins(),c.winRate())).toList();
        return new Snapshot(account.path("gameName").asString()+"#"+account.path("tagLine").asString(),icon,rank,
            new RiotStats.Sample(sample.games(),named,sample.modeGames()),0,through,
            RiotStats.QUEUES,null,null,highest,mastery,splitStart,history.complete(),sample.wins());
    }
}
