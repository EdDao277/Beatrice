package com.beatrice.backend.recommendation;

import java.util.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.stereotype.Service;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.*;
import com.beatrice.backend.champion.ChampionCatalog;
import com.beatrice.backend.team.*;
import com.beatrice.backend.game.*;
import static com.beatrice.backend.game.GameData.*;
import static org.springframework.http.HttpStatus.BAD_REQUEST;

@Service @Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ)
public class RecommendationService {
    public record Request(@NotNull Format format,@NotNull Side side,@NotNull TeamData.Role targetRole,int queueId,
        @NotBlank String patch,String datasetId,@NotNull @Size(max=20) List<@NotNull @Valid Action> actions,
        @NotNull @Size(max=10) List<@NotNull @Valid Assignment> assignments,
        @NotNull @Size(max=5) Set<@NotBlank String> intendedPicks,@NotNull @Size(max=10) Set<@NotBlank String> desiredTraits) {}
    public record Dataset(String id,long metadataImportId,long splitStart) {}
    public record Response(List<WeightedRecommendations.Pick> picks,List<RecommendationEngine.Candidate> bans,
        String datasetId,String patch,int queueId,Long metadataImportId,List<String> notices,String algorithm) {}
    private final JdbcTemplate jdbc;private final TeamService teams;private final ChampionCatalog catalog;private final ObjectMapper mapper;
    public RecommendationService(JdbcTemplate jdbc,TeamService teams,ChampionCatalog catalog,ObjectMapper mapper) {this.jdbc=jdbc;this.teams=teams;this.catalog=catalog;this.mapper=mapper;}
    public List<Dataset> datasets() {return jdbc.query("select id,metadata_import_id,split_start from collection_datasets order by split_start desc,id",(rs,n)->new Dataset(rs.getString(1),rs.getLong(2),rs.getLong(3)));}
    public Response recommend(long teamId,Request request) {
        if(!catalog.catalog().version().equals(request.patch())) fail("Champion patch changed; reload the draft.");
        if(!List.of(400,420,440,710).contains(request.queueId()) || (request.format()==Format.RANKED && request.queueId()==710)) fail("Select a compatible game queue.");
        DraftRules.validatePrefix(request.format(),request.actions(),catalog);
        var team=teams.get(teamId);var player=team.players().stream().filter(p->p.role()==request.targetRole()).findFirst().orElseThrow();
        var unavailable=new HashSet<String>();var allies=new HashMap<String,String>();var enemies=new HashMap<String,String>();
        for(var action:request.actions()) if(action.championId()!=null) unavailable.add(action.championId());
        for(var a:request.assignments()) {
            if(request.actions().stream().noneMatch(p->p.kind()==Kind.PICK && p.side()==a.side() && a.championId().equals(p.championId()))) fail("Only picked champions can be assigned a role.");
            var map=a.side()==request.side()?allies:enemies;
            if(map.containsKey(a.championId()) || map.containsValue(a.role().name())) fail("Duplicate champion or role assignment.");
            map.put(a.championId(),a.role().name());
        }
        for(String id:request.intendedPicks()) catalog.require(id);
        Long metadataImport;
        if(request.datasetId()!=null && !request.datasetId().isBlank()) {
            var rows=jdbc.queryForList("select metadata_import_id from collection_datasets where id=?",Long.class,request.datasetId());
            if(rows.isEmpty()) throw new ResponseStatusException(BAD_REQUEST,"Unknown evidence dataset.");
            metadataImport=rows.getFirst();
        } else metadataImport=jdbc.queryForObject("select max(import_id) from reference_champion_metadata",Long.class);
        var traits=new HashMap<String,Set<String>>();
        if(metadataImport!=null) jdbc.query("select champion_id,raw_metadata::text from reference_champion_metadata where import_id=?",rs->{
            var node=mapper.readTree(rs.getString(2));var tags=new HashSet<String>();
            boolean known=node.hasNonNull("utility_tags") && node.hasNonNull("comp_tags")
                && Set.of("AP","AD","Mixed","True").contains(node.path("damage_type").asString());
            for(String field:List.of("utility_tags","comp_tags")) {
                var value=node.path(field);
                if(value.isArray()) value.forEach(v->tags.add(v.asString()));
                else for(String tag:value.asString().replaceAll("[{}\\[\\]\"]","").split(",")) if(!tag.isBlank()) tags.add(tag.strip());
            }
            String damage=node.path("damage_type").asString();
            if(damage.equals("AP") || damage.equals("Mixed")) tags.add("AP");
            if(damage.equals("AD") || damage.equals("Mixed")) tags.add("AD");
            if(known) traits.put(rs.getString(1),Set.copyOf(tags));
        },metadataImport);
        var pool=new ArrayList<RecommendationEngine.Champion>();
        for(var entry:player.champions()) {
            var champion=catalog.findByName(entry.name());
            if(champion!=null) pool.add(new RecommendationEngine.Champion(champion.id(),entry.comfort(),traits.getOrDefault(champion.id(),Set.of())));
        }
        var covered=new HashSet<String>();boolean allAllyMetadata=true;
        for(var action:request.actions()) if(action.kind()==Kind.PICK && action.side()==request.side()) {
            allAllyMetadata &= traits.containsKey(action.championId());covered.addAll(traits.getOrDefault(action.championId(),Set.of()));
        }
        String[] parts=request.patch().split("\\.");String patch=parts.length>=2?parts[0]+"."+parts[1]:request.patch();
        var evidence=new ArrayList<RecommendationEngine.Evidence>();
        if(request.datasetId()!=null && !request.datasetId().isBlank()) for(String kind:List.of("ROLE","SYNERGY","MATCHUP")) {
            String table=switch(kind) {case "ROLE"->"champion_role_stats";case "SYNERGY"->"champion_synergy_stats";default->"champion_matchup_stats";};
            evidence.addAll(jdbc.query("select champion_id,role,partner_id,partner_role,games,wins from "+table+" where dataset_id=? and patch=? and queue_id=?",
                (rs,n)->new RecommendationEngine.Evidence(kind,rs.getString(1),rs.getString(2),rs.getString(3),rs.getString(4),rs.getLong(5),rs.getLong(6)),request.datasetId(),patch,request.queueId()));
        }
        var context=new RecommendationEngine.Context(request.targetRole().name(),pool,unavailable,request.intendedPicks(),request.desiredTraits(),covered,allies,enemies,evidence);
        var notices=new ArrayList<String>();notices.add("Preference score, not win probability. Coverage is available factor weight, not statistical confidence.");
        if(evidence.isEmpty()) notices.add("No maintained statistics for the selected dataset, patch and queue. Unknown factors stay neutral.");
        notices.add("Pro data, team-history scoring and draft-value scoring are not connected. No LLM is running.");
        if(!allAllyMetadata) notices.add("Ally metadata is incomplete; composition scoring is neutral.");
        long ownPicks=request.actions().stream().filter(a->a.side()==request.side() && a.kind()==Kind.PICK).count();
        long ownBans=request.actions().stream().filter(a->a.side()==request.side() && a.kind()==Kind.BAN).count();
        var picks=allies.containsValue(request.targetRole().name()) || ownPicks==5?List.<WeightedRecommendations.Pick>of():new WeightedRecommendations().score(context,allAllyMetadata?traits.keySet():Set.of());
        var bans=ownBans==5?List.<RecommendationEngine.Candidate>of():new RecommendationEngine().recommend(context).bans();
        return new Response(picks,bans,request.datasetId(),patch,request.queueId(),metadataImport,List.copyOf(notices),"weighted-picks-v2 / evidence-bans-v1");
    }
    private void fail(String message) {throw new ResponseStatusException(BAD_REQUEST,message);}
}
