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
import static org.hamcrest.Matchers.*;

@SpringBootTest @Import(TestDatabase.class) @AutoConfigureMockMvc @Transactional
class TeamBanApiTest {
    @Autowired MockMvc mvc; @Autowired TeamService teams; @Autowired org.springframework.jdbc.core.JdbcTemplate jdbc;
    private long fixture() {
        var team=teams.create(new TeamData.Create("Ban fixture"));
        teams.update(team.id(),new TeamData.Update(team.name(),team.version(),team.players().stream().map(p->
            p.role()==TeamData.Role.MID || p.role()==TeamData.Role.BOT ? new TeamData.Player(p.role(),"Player","",java.util.List.of(new TeamData.Champion(p.role()==TeamData.Role.MID?"Champion 0":"Champion 1",10))):p).toList()));
        long archive=jdbc.queryForObject("insert into reference_imports(sha256,filename) values ('ban-fixture','fixture') returning id",Long.class);
        for(int i=2;i<10;i++)jdbc.update("insert into reference_champion_metadata values (?, ?, '[]'::jsonb, ?::jsonb)",archive,"C"+i,"{\"counters\":\"{Champion 0,c1}\"}");
        jdbc.update("insert into collection_datasets(id,split_start,metadata_import_id) values ('ban-fixture',1,?)",archive);
        return team.id();
    }
    private org.springframework.test.web.servlet.ResultActions request(long id,String format,String actions) throws Exception {
        return mvc.perform(post("/api/teams/"+id+"/draft/bans").contentType("application/json").content(
            "{\"format\":\""+format+"\",\"side\":\"BLUE\",\"patch\":\"test\",\"actions\":["+actions+"]}"));
    }
    @Test void returnsSixNormalizedFallbacksAndHonorsDuplicateBanRules() throws Exception {
        long id=fixture();var before=teams.get(id);
        request(id,"TOURNAMENT","").andExpect(status().isOk()).andExpect(jsonPath("$.bans",hasSize(6)))
            .andExpect(jsonPath("$.bans[0].championId").value("C2"))
            .andExpect(jsonPath("$.bans[0].basis").value("POOL_COMPOSITION_FALLBACK"))
            .andExpect(jsonPath("$.bans[0].evidence").isEmpty());
        request(id,"TOURNAMENT","{\"kind\":\"BAN\",\"side\":\"BLUE\",\"championId\":\"C2\"}")
            .andExpect(status().isOk()).andExpect(jsonPath("$.bans[*].championId",not(hasItem("C2"))));
        request(id,"RANKED","{\"kind\":\"BAN\",\"side\":\"RED\",\"championId\":\"C2\"}")
            .andExpect(status().isOk()).andExpect(jsonPath("$.bans[0].championId").value("C2"));
        org.junit.jupiter.api.Assertions.assertEquals(before,teams.get(id));
    }
    @Test void selectsOneExactPatchSliceAndPrioritizesStatistics() throws Exception {
        long id=fixture();
        jdbc.update("insert into champion_role_stats(dataset_id,patch,queue_id,champion_id,role,games,wins) values ('ban-fixture','test',400,'C9','MID',100,70),('ban-fixture','old',420,'C8','MID',1000,999)");
        request(id,"TOURNAMENT","").andExpect(status().isOk()).andExpect(jsonPath("$.queueId").value(400))
            .andExpect(jsonPath("$.bans[0].championId").value("C9"))
            .andExpect(jsonPath("$.bans[0].basis").value("EVIDENCE_BACKED"))
            .andExpect(jsonPath("$.bans[1].basis").value("POOL_COMPOSITION_FALLBACK"));
    }
    @Test void abstainsDuringPicksAndRejectsIllegalDrafts() throws Exception {
        long id=fixture();var actions=new java.util.ArrayList<String>();
        for(int i=0;i<6;i++)actions.add("{\"kind\":\"BAN\",\"side\":\""+(i%2==0?"BLUE":"RED")+"\",\"championId\":null}");
        request(id,"TOURNAMENT",String.join(",",actions)).andExpect(status().isOk()).andExpect(jsonPath("$.bans").isEmpty());
        request(id,"TOURNAMENT","{\"kind\":\"PICK\",\"side\":\"BLUE\",\"championId\":\"C0\"}").andExpect(status().isBadRequest());
        request(id,"TOURNAMENT","{\"kind\":\"BAN\",\"side\":\"BLUE\",\"championId\":\"Unknown\"}").andExpect(status().isBadRequest());
    }
    @Test void lateTournamentBansExcludeEveryExistingPickAndBan() throws Exception {
        long id=fixture();var actions=new java.util.ArrayList<String>();
        String[] sides="BLUE RED BLUE RED BLUE RED BLUE RED RED BLUE BLUE RED".split(" ");
        for(int i=0;i<12;i++)actions.add("{\"kind\":\""+(i<6?"BAN":"PICK")+"\",\"side\":\""+sides[i]+"\",\"championId\":"+(i<6?"null":"\"C"+(i-4)+"\"")+"}");
        request(id,"TOURNAMENT",String.join(",",actions)).andExpect(status().isOk())
            .andExpect(jsonPath("$.bans[*].championId",contains("C8","C9")));
    }
}
