package com.beatrice.backend.recommendation;

import java.util.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;
import com.beatrice.backend.champion.ChampionCatalog;
import com.beatrice.backend.team.TeamService;
import com.beatrice.backend.game.DraftRules;
import static com.beatrice.backend.game.GameData.*;
import static org.springframework.http.HttpStatus.BAD_REQUEST;

/** Team-wide picks only. The older role-specific recommendation/ban endpoint is untouched. */
@Service
@Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ)
public class TeamPickService {
    public record Request(@NotNull Format format,@NotNull Side side,@NotBlank String patch,
        @NotNull @Size(max=20) List<@NotNull @Valid Action> actions,
        Integer queueId,String datasetId,@Size(max=10) Set<@NotBlank String> desiredTraits) {}
    public record Pick(String championId,double javaScore,double mlBonus,double score,double coverage,
        Map<String,WeightedRecommendations.Component> components,List<String> warnings,List<RecommendationEngine.Evidence> evidence,
        Set<String> feasibleRoles,String scoringRole,String mlEvidenceQuality) {}
    public record Response(String requestId,List<Pick> picks,String modelVersion,String algorithm) {}
    private final TeamService teams;private final ChampionCatalog catalog;private final PickModelClient ml;
    private final JdbcTemplate jdbc;private final ObjectMapper mapper;
    private final PickDiagnostics diagnostics;
    public TeamPickService(TeamService teams,ChampionCatalog catalog,PickModelClient ml,JdbcTemplate jdbc,ObjectMapper mapper,PickDiagnostics diagnostics) {
        this.teams=teams;this.catalog=catalog;this.ml=ml;this.jdbc=jdbc;this.mapper=mapper;this.diagnostics=diagnostics;
    }
    public Response recommend(long teamId,Request request) {
        if(!catalog.catalog().version().equals(request.patch())) fail("Champion patch changed; reload the draft.");
        DraftRules.validatePrefix(request.format(),request.actions(),catalog);
        var team=teams.get(teamId);
        var allies=request.actions().stream().filter(a->a.kind()==Kind.PICK && a.side()==request.side()).map(Action::championId).toList();
        var enemies=request.actions().stream().filter(a->a.kind()==Kind.PICK && a.side()!=request.side()).map(Action::championId).toList();
        var unavailable=new HashSet<String>();request.actions().forEach(a->{if(a.championId()!=null) unavailable.add(a.championId());});
        var pools=new TreeMap<String,Map<String,Integer>>();
        for(var player:team.players()) {
            var pool=new TreeMap<String,Integer>();
            for(var entry:player.champions()) {
                var champion=catalog.findByName(entry.name());
                if(champion!=null) pool.put(champion.id(),entry.comfort());
            }
            pools.put(player.role().name(),pool);
        }
        var membership=new TreeMap<String,Set<String>>();pools.forEach((role,pool)->membership.put(role,pool.keySet()));
        var feasible=TeamPickFeasibility.candidates(membership,allies,unavailable);
        String requestId=UUID.randomUUID().toString();
        if(feasible.isEmpty()) {
            diagnostics.record(requestId,teamId,List.of(),GuardedPickBonus.fallback(List.of(),"NO_LEGAL_CANDIDATES"),0);
            return new Response(requestId,List.of(),PickModelClient.MODEL,"guarded-team-picks-v1");
        }
        String patch=request.patch().split("\\.").length>=2?String.join(".",Arrays.copyOf(request.patch().split("\\."),2)):request.patch();
        var slice=readEvidence(request,patch);
        var covered=new HashSet<String>();boolean knownAllies=true;
        for(String ally:allies) {knownAllies &= slice.traits().containsKey(ally);covered.addAll(slice.traits().getOrDefault(ally,Set.of()));}
        var details=new HashMap<String,WeightedRecommendations.Pick>();var scoringRoles=new HashMap<String,String>();
        var scorer=new WeightedRecommendations();
        for(var candidate:feasible.entrySet()) for(String role:candidate.getValue()) {
            var champion=new RecommendationEngine.Champion(candidate.getKey(),pools.get(role).get(candidate.getKey()),slice.traits().getOrDefault(candidate.getKey(),Set.of()));
            // This is a scoring hypothesis only. Feasible assignments never become known lane evidence.
            var context=new RecommendationEngine.Context(role,List.of(champion),unavailable,Set.of(),
                request.desiredTraits()==null?Set.of():request.desiredTraits(),covered,Map.of(),Map.of(),slice.evidence());
            var scored=scorer.score(context,knownAllies?slice.traits().keySet():Set.of()).getFirst();
            var prior=details.get(candidate.getKey());
            if(prior==null || scored.score()>prior.score()) {details.put(candidate.getKey(),scored);scoringRoles.put(candidate.getKey(),role);}
        }
        var bases=details.values().stream().sorted(Comparator.comparingDouble(WeightedRecommendations.Pick::score).reversed().thenComparing(WeightedRecommendations.Pick::championId))
            .map(p->new GuardedPickBonus.Base(p.championId(),p.score())).toList();
        var inference=ml.rank(requestId,patch,allies,enemies,bases.stream().map(GuardedPickBonus.Base::championId).toList());
        var guarded=inference.signals()==null?GuardedPickBonus.fallback(bases,inference.status()):GuardedPickBonus.apply(bases,inference.signals());
        diagnostics.record(requestId,teamId,bases,guarded,inference);
        var picks=guarded.picks().stream().limit(3).map(p->{
            var base=details.get(p.championId());
            return new Pick(p.championId(),p.javaScore(),p.mlBonus(),p.score(),base.coverage(),base.components(),base.warnings(),base.evidence(),
                feasible.get(p.championId()),scoringRoles.get(p.championId()),p.mlEvidenceQuality());
        }).toList();
        return new Response(requestId,picks,PickModelClient.MODEL,"guarded-team-picks-v1");
    }
    private record Slice(Map<String,Set<String>> traits,List<RecommendationEngine.Evidence> evidence) {}
    private Slice readEvidence(Request request,String patch) {
        Long metadata=jdbc.queryForObject("select max(import_id) from reference_champion_metadata",Long.class);
        boolean selected=request.datasetId()!=null && !request.datasetId().isBlank();
        if(selected) {
            if(request.queueId()==null || !Set.of(400,420,440,710).contains(request.queueId())
                || (request.format()==Format.RANKED && request.queueId()==710)) fail("Select a compatible statistics queue.");
            var ids=jdbc.queryForList("select metadata_import_id from collection_datasets where id=?",Long.class,request.datasetId());
            if(ids.isEmpty()) fail("Unknown evidence dataset.");metadata=ids.getFirst();
        }
        var traits=new HashMap<String,Set<String>>();
        if(metadata!=null) jdbc.query("select champion_id,raw_metadata::text from reference_champion_metadata where import_id=?",rs->{
            var node=mapper.readTree(rs.getString(2));String damage=node.path("damage_type").asString();
            if(!node.hasNonNull("utility_tags") || !node.hasNonNull("comp_tags") || !Set.of("AP","AD","Mixed","True").contains(damage)) return;
            var tags=new HashSet<String>();
            for(String field:List.of("utility_tags","comp_tags")) {
                var value=node.path(field);
                if(value.isArray()) value.forEach(v->tags.add(v.asString()));
                else for(String tag:value.asString().replaceAll("[{}\\[\\]\"]","").split(",")) if(!tag.isBlank()) tags.add(tag.strip());
            }
            if(damage.equals("AP") || damage.equals("Mixed")) tags.add("AP");
            if(damage.equals("AD") || damage.equals("Mixed")) tags.add("AD");
            traits.put(rs.getString(1),Set.copyOf(tags));
        },metadata);
        var evidence=new ArrayList<RecommendationEngine.Evidence>();
        // No queue is inferred from draft format. Unknown lanes never become pair-stat assignments.
        if(selected) for(String kind:List.of("ROLE","SYNERGY","MATCHUP")) {
            String table=switch(kind) {case "ROLE"->"champion_role_stats";case "SYNERGY"->"champion_synergy_stats";default->"champion_matchup_stats";};
            evidence.addAll(jdbc.query("select champion_id,role,partner_id,partner_role,games,wins from "+table+" where dataset_id=? and patch=? and queue_id=?",
                (rs,n)->new RecommendationEngine.Evidence(kind,rs.getString(1),rs.getString(2),rs.getString(3),rs.getString(4),rs.getLong(5),rs.getLong(6)),request.datasetId(),patch,request.queueId()));
        }
        return new Slice(traits,evidence);
    }
    private static void fail(String message) {throw new ResponseStatusException(BAD_REQUEST,message);}
}
