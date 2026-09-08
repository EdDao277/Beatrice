package com.beatrice.backend.recommendation;
import com.beatrice.backend.TestDatabase;
import com.beatrice.backend.team.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest @Import(TestDatabase.class) @AutoConfigureMockMvc @Transactional
class RecommendationApiTest {
    @Autowired MockMvc mvc;
    @Autowired TeamService teams;
    @Autowired org.springframework.jdbc.core.JdbcTemplate jdbc;
    @Test void readsSavedPoolAndOnlyTheRequestedEvidenceSlice() throws Exception {
        var team=teams.create(new TeamData.Create("Evidence fixture"));
        teams.update(team.id(),new TeamData.Update(team.name(),team.version(),team.players().stream().map(p ->
            p.role()==TeamData.Role.MID ? new TeamData.Player(p.role(),"Fixture player","",java.util.List.of(new TeamData.Champion("Champion 0",8))) : p).toList()));
        long archive=jdbc.queryForObject("insert into reference_imports(sha256,filename) values ('recommendation-fixture','fixture') returning id",Long.class);
        jdbc.update("insert into reference_champion_metadata values (?, 'C0', '[]'::jsonb, '{\"damage_type\":\"AP\",\"comp_tags\":[],\"utility_tags\":[]}'::jsonb)",archive);
        jdbc.update("insert into collection_datasets(id,split_start,metadata_import_id) values ('recommendation-fixture',1,?)",archive);
        jdbc.update("insert into champion_role_stats(dataset_id,patch,queue_id,champion_id,role,games,wins) values ('recommendation-fixture','test',400,'C0','MID',100,60)");
        String path="/api/teams/"+team.id()+"/draft/recommendations";
        String body="""
            {"format":"RANKED","side":"BLUE","targetRole":"MID","queueId":400,"patch":"test",
            "datasetId":"recommendation-fixture","actions":[],"assignments":[],"intendedPicks":[],"desiredTraits":["AP"]}
            """;
        mvc.perform(post(path).contentType("application/json").content(body)).andExpect(status().isOk())
            .andExpect(jsonPath("$.picks[0].championId").value("C0"))
            .andExpect(jsonPath("$.picks[0].components.meta.available").value(true))
            .andExpect(jsonPath("$.picks[0].components.composition.value").value(100))
            .andExpect(jsonPath("$.picks[0].coverage").value(63));
        mvc.perform(post(path).contentType("application/json").content(body.replace("400","420"))).andExpect(status().isOk())
            .andExpect(jsonPath("$.picks[0].components.meta.value").value(50))
            .andExpect(jsonPath("$.picks[0].components.meta.available").value(false))
            .andExpect(jsonPath("$.picks[0].coverage").value(55));
        jdbc.update("update reference_champion_metadata set raw_metadata=jsonb_set(raw_metadata,'{damage_type}','\"Unknown\"'::jsonb) where import_id=?",archive);
        mvc.perform(post(path).contentType("application/json").content(body)).andExpect(status().isOk())
            .andExpect(jsonPath("$.picks[0].components.composition.value").value(50))
            .andExpect(jsonPath("$.picks[0].components.composition.available").value(false));
        var actions=new java.util.ArrayList<String>();
        for(int i=0;i<10;i++) actions.add("{\"kind\":\"BAN\",\"side\":\""+(i<5?"BLUE":"RED")+"\",\"championId\":null}");
        String[] turns="BLUE RED RED BLUE BLUE RED RED BLUE BLUE".split(" ");
        for(int i=0;i<turns.length;i++) actions.add("{\"kind\":\"PICK\",\"side\":\""+turns[i]+"\",\"championId\":\"C"+(i+1)+"\"}");
        mvc.perform(post(path).contentType("application/json").content(body.replace("\"actions\":[]","\"actions\":["+String.join(",",actions)+"]")))
            .andExpect(status().isOk()).andExpect(jsonPath("$.picks").isEmpty()).andExpect(jsonPath("$.bans").isEmpty());
        mvc.perform(post(path).contentType("application/json").content(body.replace("\"assignments\":[]","\"assignments\":[{\"side\":\"BLUE\",\"championId\":\"C0\",\"role\":\"MID\"}]")))
            .andExpect(status().isBadRequest());
    }
    @Test void missingDataIsAllowedButIllegalDraftAndQueueAreRejected() throws Exception {
        var team=teams.create(new TeamData.Create("Recommendation fixture"));
        String path="/api/teams/"+team.id()+"/draft/recommendations";
        String body="{\"format\":\"RANKED\",\"side\":\"BLUE\",\"targetRole\":\"MID\",\"queueId\":400,\"patch\":\"test\",\"actions\":[],\"assignments\":[],\"intendedPicks\":[],\"desiredTraits\":[]}";
        mvc.perform(post(path).contentType("application/json").content(body)).andExpect(status().isOk()).andExpect(jsonPath("$.picks").isEmpty());
        mvc.perform(post(path).contentType("application/json").content(body.replace("400","450"))).andExpect(status().isBadRequest());
        mvc.perform(post(path).contentType("application/json").content(body.replace("\"actions\":[]","\"actions\":[{\"kind\":\"PICK\",\"side\":\"BLUE\",\"championId\":\"C0\"}]"))).andExpect(status().isBadRequest());
    }
}
