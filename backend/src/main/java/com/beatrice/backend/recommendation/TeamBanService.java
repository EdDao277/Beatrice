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
import com.beatrice.backend.team.TeamService;
import com.beatrice.backend.game.DraftRules;
import static com.beatrice.backend.game.GameData.*;
import static org.springframework.http.HttpStatus.BAD_REQUEST;

/** Read-only ban advice, independent of the pick model and its availability. */
@Service @Transactional(readOnly=true,isolation=Isolation.REPEATABLE_READ)
public class TeamBanService {
    public record Request(@NotNull Format format,@NotNull Side side,@NotBlank String patch,
        @NotNull @Size(max=20) List<@NotNull @Valid Action> actions) {}
    public record Response(List<BanRecommendations.Ban> bans,String datasetId,Integer queueId,String patch,
        Long metadataImportId,List<String> notices) {}
    private record Slice(String id,int queue,long metadata) {}
    private final JdbcTemplate jdbc;private final TeamService teams;private final ChampionCatalog catalog;private final ObjectMapper mapper;
    public TeamBanService(JdbcTemplate jdbc,TeamService teams,ChampionCatalog catalog,ObjectMapper mapper) {
        this.jdbc=jdbc;this.teams=teams;this.catalog=catalog;this.mapper=mapper;
    }
    public Response recommend(long teamId,Request request) {
        if(!catalog.catalog().version().equals(request.patch()))throw new ResponseStatusException(BAD_REQUEST,"Reload the champion catalog.");
        DraftRules.validatePrefix(request.format(),request.actions(),catalog);
        var team=teams.get(teamId);
        int n=request.actions().size();
        boolean ban=request.format()==Format.RANKED?n<10:n<6 || (n>=12 && n<16);
        if(!ban || request.actions().stream().filter(a->a.kind()==Kind.BAN && a.side()==request.side()).count()>=5)
            return new Response(List.of(),null,null,request.patch(),null,List.of());
        var unavailable=new HashSet<String>();
        for(var a:request.actions())if(a.championId()!=null && (request.format()!=Format.RANKED || a.side()==request.side()))unavailable.add(a.championId());
        var aliases=new HashMap<String,String>();var ids=new HashSet<String>();
        for(var c:catalog.catalog().champions()) {ids.add(c.id());aliases.put(key(c.id()),c.id());aliases.put(key(c.name()),c.id());}
        var pools=new TreeMap<String,List<RecommendationEngine.Champion>>();
        for(var player:team.players()) {
            var pool=new ArrayList<RecommendationEngine.Champion>();
            for(var c:player.champions()) {var id=aliases.get(key(c.name()));if(id!=null)pool.add(new RecommendationEngine.Champion(id,c.comfort(),Set.of()));}
            pools.put(player.role().name(),pool);
        }
        String[] parts=request.patch().split("\\.");String patch=parts.length>=2?parts[0]+"."+parts[1]:request.patch();
        // Select ONE exact-patch reference slice by coverage, never by favorable win rate.
        // Tournament format is not a queue identity; disclose the selected reference queue.
        var slices=jdbc.query("""
            select s.dataset_id,s.queue_id,d.metadata_import_id from (
              select dataset_id,queue_id,count(*) coverage from (
                select dataset_id,queue_id from champion_role_stats where patch=? and games>=30
                union all
                select dataset_id,queue_id from champion_matchup_stats where patch=? and games>=30
              ) rows where queue_id in (400,420,440,710) group by dataset_id,queue_id
            ) s join collection_datasets d on d.id=s.dataset_id
            order by s.coverage desc,d.split_start desc,s.dataset_id,s.queue_id limit 1
            """,(rs,i)->new Slice(rs.getString(1),rs.getInt(2),rs.getLong(3)),patch,patch);
        Slice slice=slices.isEmpty()?null:slices.getFirst();
        Long metadataId=slice==null?jdbc.queryForObject("select max(import_id) from reference_champion_metadata",Long.class):slice.metadata();
        var metadata=new HashMap<String,BanRecommendations.Metadata>();
        if(metadataId!=null)jdbc.query("select champion_id,raw_metadata::text from reference_champion_metadata where import_id=?",rs->{
            String id=aliases.get(key(rs.getString(1)));if(id==null)return;
            var node=mapper.readTree(rs.getString(2));
            metadata.put(id,new BanRecommendations.Metadata(normalize(tags(node,"counters"),aliases),normalize(tags(node,"countered_by"),aliases),tags(node,"comp_tags"),tags(node,"counter_tags")));
        },metadataId);
        var evidence=new ArrayList<RecommendationEngine.Evidence>();
        if(slice!=null)for(String kind:List.of("ROLE","MATCHUP")) {
            String table=kind.equals("ROLE")?"champion_role_stats":"champion_matchup_stats";
            evidence.addAll(jdbc.query("select champion_id,role,partner_id,partner_role,games,wins from "+table+" where dataset_id=? and patch=? and queue_id=?",
                (rs,i)->new RecommendationEngine.Evidence(kind,rs.getString(1),rs.getString(2),rs.getString(3),rs.getString(4),rs.getLong(5),rs.getLong(6)),slice.id(),patch,slice.queue()));
        }
        var bans=new BanRecommendations().rank(pools,metadata,evidence,unavailable,ids);
        return new Response(bans,slice==null?null:slice.id(),slice==null?null:slice.queue(),patch,metadataId,
            List.of("Reference statistics use one exact-patch dataset/queue, not necessarily this game's queue.",
                "Pool/composition fallback uses curated relationships, not measured win rates. Opponent pools are unknown."));
    }
    private static String key(String value) {return value.replaceAll("[^A-Za-z0-9]","").toLowerCase(Locale.ROOT);}
    private static Set<String> normalize(Set<String> values,Map<String,String> aliases) {
        var result=new HashSet<String>();for(String v:values){String id=aliases.get(key(v));if(id!=null)result.add(id);}return result;
    }
    private static Set<String> tags(JsonNode node,String field) {
        var result=new HashSet<String>();var value=node.path(field);
        if(value.isArray())value.forEach(v->result.add(v.asString().strip()));
        else for(String tag:value.asString().replaceAll("[{}\\[\\]\"]","").split(","))if(!tag.isBlank())result.add(tag.strip());
        return result;
    }
}
