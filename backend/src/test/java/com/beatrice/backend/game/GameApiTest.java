package com.beatrice.backend.game;

import com.beatrice.backend.TestDatabase;
import com.beatrice.backend.team.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
@Import(TestDatabase.class)
@Transactional
class GameApiTest {
    @Autowired MockMvc mvc;
    @Autowired TeamService teams;
    @Autowired tools.jackson.databind.ObjectMapper mapper;
    @Test void annotatesOldGameRejectsWrongPicksAndStaleAssignments() throws Exception {
        long teamId=teams.create(new TeamData.Create("Ravens")).id();
        var response=mvc.perform(post("/api/teams/"+teamId+"/games").contentType("application/json")
            .content(payload("TOURNAMENT",UUID.randomUUID().toString(),true))).andReturn().getResponse();
        long id=mapper.readTree(response.getContentAsString()).path("id").asLong();
        String url="/api/teams/"+teamId+"/games/"+id+"/assignments";
        String valid="{\"version\":0,\"assignments\":[{\"side\":\"BLUE\",\"championId\":\"C6\",\"role\":\"JUNGLE\"}]}";
        mvc.perform(put(url).contentType("application/json").content(valid.replace("C6","C0"))).andExpect(status().isBadRequest());
        mvc.perform(put(url).contentType("application/json").content(valid)).andExpect(status().isOk())
            .andExpect(jsonPath("$.assignmentVersion").value(1)).andExpect(jsonPath("$.result").value("WIN"))
            .andExpect(jsonPath("$.assignments[0].role").value("JUNGLE"));
        mvc.perform(put(url).contentType("application/json").content(valid)).andExpect(status().isConflict());
        mvc.perform(put(url).contentType("application/json").content("{\"version\":1,\"assignments\":[{\"side\":\"BLUE\",\"championId\":\"C6\",\"role\":\"TOP\"},{\"side\":\"BLUE\",\"championId\":\"C9\",\"role\":\"TOP\"}]}"))
            .andExpect(status().isBadRequest());
    }
    // Literal external sequence: assertions do not reuse production rule helpers.
    private String payload(String mode, String id, boolean complete) {
        String[] sides = mode.equals("RANKED")
            ? "BLUE BLUE BLUE BLUE BLUE RED RED RED RED RED BLUE RED RED BLUE BLUE RED RED BLUE BLUE RED".split(" ")
            : "BLUE RED BLUE RED BLUE RED BLUE RED RED BLUE BLUE RED RED BLUE RED BLUE RED BLUE BLUE RED".split(" ");
        var events = new ArrayList<String>();
        for (int n = 0; n < (complete ? 20 : 19); n++) {
            boolean ban = mode.equals("RANKED") ? n < 10 : n < 6 || (n >= 12 && n < 16);
            events.add("{\"kind\":\"%s\",\"side\":\"%s\",\"championId\":\"C%d\"}".formatted(ban ? "BAN" : "PICK", sides[n], n));
        }
        return "{\"requestId\":\"%s\",\"format\":\"%s\",\"side\":\"RED\",\"result\":\"WIN\",\"patch\":\"test\",\"actions\":[%s]}".formatted(id, mode, String.join(",", events));
    }
    @Test void savesBothFormatsAndIsolatesTeams() throws Exception {
        long id = teams.create(new TeamData.Create("Ravens")).id();
        long other = teams.create(new TeamData.Create("Other")).id();
        for (String mode : List.of("RANKED", "TOURNAMENT")) {
            mvc.perform(post("/api/teams/" + id + "/games").contentType("application/json").content(payload(mode, UUID.randomUUID().toString(), true)))
                .andExpect(status().isCreated()).andExpect(jsonPath("$.format").value(mode))
                .andExpect(jsonPath("$.roster.name").value("Ravens"))
                .andExpect(jsonPath("$.championNames.C0").value("Champion 0"))
                .andExpect(jsonPath("$.actions.length()").value(20));
        }
        mvc.perform(get("/api/teams/" + id + "/games")).andExpect(jsonPath("$.length()").value(2));
        mvc.perform(get("/api/teams/" + other + "/games")).andExpect(jsonPath("$.length()").value(0));
    }
    @Test void retryDoesNotRecordTheSameGameTwice() throws Exception {
        long id = teams.create(new TeamData.Create("Ravens")).id();
        String body = payload("TOURNAMENT", UUID.randomUUID().toString(), true);
        for (int n=0; n<2; n++) mvc.perform(post("/api/teams/" + id + "/games").contentType("application/json").content(body)).andExpect(status().isCreated());
        mvc.perform(get("/api/teams/" + id + "/games")).andExpect(jsonPath("$.length()").value(1));
        mvc.perform(post("/api/teams/" + id + "/games").contentType("application/json").content(body.replace("WIN", "LOSS")))
            .andExpect(status().isConflict());
    }
    @Test void rejectsIncompleteDuplicateUnknownAndWrongOrder() throws Exception {
        long id = teams.create(new TeamData.Create("Ravens")).id();
        String body = payload("TOURNAMENT", UUID.randomUUID().toString(), true);
        for (String invalid : List.of(payload("TOURNAMENT", UUID.randomUUID().toString(), false),
            body.replace("C1\"", "C0\""), body.replace("C1\"", "Unknown\""),
            body.replaceFirst("BLUE", "RED"), body.replace("\"test\"", "\"wrong-patch\""))) {
            mvc.perform(post("/api/teams/" + id + "/games").contentType("application/json").content(invalid)).andExpect(status().isBadRequest());
        }
        mvc.perform(get("/api/teams/" + id + "/games")).andExpect(jsonPath("$.length()").value(0));
    }
}
