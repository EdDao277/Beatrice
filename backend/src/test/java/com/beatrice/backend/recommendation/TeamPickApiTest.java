package com.beatrice.backend.recommendation;

import com.beatrice.backend.TestDatabase;
import com.beatrice.backend.team.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest @Import(TestDatabase.class) @AutoConfigureMockMvc @Transactional
class TeamPickApiTest {
    @Autowired MockMvc mvc;
    @Autowired TeamService teams;
    @MockitoBean PickModelClient model;
    @BeforeEach void unavailableByDefault() {
        when(model.rank(anyString(),anyString(),anyList(),anyList(),anyList()))
            .thenReturn(new PickModelClient.Result(null,"ML_UNAVAILABLE",1));
    }
    @Test void guardsFullCandidateRankingAndPreservesColdCandidate() throws Exception {
        var team=teams.create(new TeamData.Create("Guarded ranking fixture"));
        teams.update(team.id(),new TeamData.Update(team.name(),team.version(),team.players().stream().map(p->
            new TeamData.Player(p.role(),"Fixture","",p.role()==TeamData.Role.TOP?List.of(
                new TeamData.Champion("Champion 0",10),new TeamData.Champion("Champion 1",10),
                new TeamData.Champion("Champion 2",9),new TeamData.Champion("Champion 3",9)):List.of())).toList()));
        when(model.rank(anyString(),anyString(),anyList(),anyList(),anyList())).thenAnswer(call -> {
            List<String> ids=call.getArgument(4);
            // Literal priorities: C1 breaks the C0 tie; C2's +2.5 cannot erase a 3.5-point comfort gap.
            var values=Map.of("C0",0.,"C1",2.,"C2",3.,"C3",1.);
            return new PickModelClient.Result(ids.stream().map(id->new GuardedPickBonus.Signal(id,values.get(id),
                id.equals("C3")?0:100,id.equals("C3")?0:10,40,!id.equals("C3"))).toList(),"VALID",1);
        });
        String url="/api/teams/"+team.id()+"/draft/picks";
        String body="{\"format\":\"RANKED\",\"side\":\"BLUE\",\"patch\":\"test\",\"actions\":[]}";
        mvc.perform(post(url).contentType("application/json").content(body)).andExpect(status().isOk())
            .andExpect(jsonPath("$.picks.length()").value(4))
            .andExpect(jsonPath("$.picks[0].championId").value("C1"))
            .andExpect(jsonPath("$.picks[0].javaScore").value(67.5))
            .andExpect(jsonPath("$.picks[1].championId").value("C0"))
            .andExpect(jsonPath("$.picks[2].championId").value("C2"))
            .andExpect(jsonPath("$.picks[2].score").value(66.5));
        String banned=body.replace("\"actions\":[]","\"actions\":[{\"kind\":\"BAN\",\"side\":\"BLUE\",\"championId\":\"C0\"}]");
        mvc.perform(post(url).contentType("application/json").content(banned)).andExpect(status().isOk())
            .andExpect(jsonPath("$.picks[2].championId").value("C3"))
            .andExpect(jsonPath("$.picks[2].mlBonus").value(0))
            .andExpect(jsonPath("$.picks[2].mlEvidenceQuality").value("INSUFFICIENT_EVIDENCE"));
    }
    @Test void returnsSixFromTheFullGuardedRankingAndSixExactJavaFallbacks() throws Exception {
        var team=teams.create(new TeamData.Create("Six picks"));
        teams.update(team.id(),new TeamData.Update(team.name(),team.version(),team.players().stream().map(p->
            new TeamData.Player(p.role(),"Fixture","",p.role()==TeamData.Role.TOP?
                java.util.stream.IntStream.range(0,8).mapToObj(i->new TeamData.Champion("Champion "+i,10)).toList():List.of())).toList()));
        when(model.rank(anyString(),anyString(),anyList(),anyList(),anyList())).thenAnswer(call->{
            List<String> ids=call.getArgument(4);
            org.junit.jupiter.api.Assertions.assertEquals(8,ids.size());
            return new PickModelClient.Result(ids.stream().map(id->new GuardedPickBonus.Signal(id,
                Double.parseDouble(id.substring(1)),100,10,40,true)).toList(),"VALID",1);
        });
        String url="/api/teams/"+team.id()+"/draft/picks";
        String body="{\"format\":\"RANKED\",\"side\":\"BLUE\",\"patch\":\"test\",\"actions\":[]}";
        mvc.perform(post(url).contentType("application/json").content(body)).andExpect(status().isOk())
            .andExpect(jsonPath("$.picks[*].championId").value(org.hamcrest.Matchers.contains("C7","C6","C5","C4","C3","C2")))
            .andExpect(jsonPath("$.picks[0].mlBonus").value(2.5))
            .andExpect(jsonPath("$.picks[*].javaScore").value(org.hamcrest.Matchers.everyItem(org.hamcrest.Matchers.is(67.5))));
        doReturn(new PickModelClient.Result(null,"ML_UNAVAILABLE",1)).when(model).rank(anyString(),anyString(),anyList(),anyList(),anyList());
        mvc.perform(post(url).contentType("application/json").content(body)).andExpect(status().isOk())
            .andExpect(jsonPath("$.picks[*].championId").value(org.hamcrest.Matchers.contains("C0","C1","C2","C3","C4","C5")))
            .andExpect(jsonPath("$.picks[*].mlBonus").value(org.hamcrest.Matchers.everyItem(org.hamcrest.Matchers.is(0.0))))
            .andExpect(jsonPath("$.picks[*].score").value(org.hamcrest.Matchers.everyItem(org.hamcrest.Matchers.is(67.5))));
    }
    @Test void usesSavedPoolMatchingWithoutTargetRoleAndKeepsComfortWhenMlUnavailable() throws Exception {
        var team=teams.create(new TeamData.Create("Guarded fixture"));
        teams.update(team.id(),new TeamData.Update(team.name(),team.version(),team.players().stream().map(p->
            new TeamData.Player(p.role(),"Fixture","",switch(p.role()) {
                case TOP -> List.of(new TeamData.Champion("Champion 0",10),new TeamData.Champion("Champion 1",8));
                case MID -> List.of(new TeamData.Champion("Champion 0",7));
                default -> List.of();
            })).toList()));
        String url="/api/teams/"+team.id()+"/draft/picks";
        String body="{\"format\":\"RANKED\",\"side\":\"BLUE\",\"patch\":\"test\",\"actions\":[]}";
        mvc.perform(post(url).contentType("application/json").content(body)).andExpect(status().isOk())
            .andExpect(jsonPath("$.picks[0].championId").value("C0"))
            .andExpect(jsonPath("$.picks[0].feasibleRoles.length()").value(2))
            .andExpect(jsonPath("$.picks[0].components.comfort.value").value(100))
            .andExpect(jsonPath("$.picks[0].javaScore").value(67.5))
            .andExpect(jsonPath("$.picks[0].mlBonus").value(0))
            .andExpect(jsonPath("$.picks[0].score").value(67.5))
            .andExpect(jsonPath("$.picks[0].probability").doesNotExist());
        var actions=new ArrayList<String>();
        for(int i=0;i<10;i++) actions.add("{\"kind\":\"BAN\",\"side\":\""+(i<5?"BLUE":"RED")+"\",\"championId\":null}");
        actions.add("{\"kind\":\"PICK\",\"side\":\"BLUE\",\"championId\":\"C0\"}");
        mvc.perform(post(url).contentType("application/json").content(body.replace("\"actions\":[]","\"actions\":["+String.join(",",actions)+"]")))
            .andExpect(status().isOk()).andExpect(jsonPath("$.picks.length()").value(1))
            .andExpect(jsonPath("$.picks[0].championId").value("C1"));
        mvc.perform(post(url).contentType("application/json").content(body.replace("\"actions\":[]","\"actions\":[{\"kind\":\"BAN\",\"side\":\"BLUE\",\"championId\":\"C1\"}]")))
            .andExpect(status().isOk()).andExpect(jsonPath("$.picks.length()").value(1))
            .andExpect(jsonPath("$.picks[0].championId").value("C0"));
    }
}
