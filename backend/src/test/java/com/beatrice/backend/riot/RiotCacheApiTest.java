package com.beatrice.backend.riot;
import com.beatrice.backend.TestDatabase;
import com.beatrice.backend.team.TeamService;
import com.beatrice.backend.team.TeamData;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.transaction.annotation.Transactional;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest @Import(TestDatabase.class) @AutoConfigureMockMvc @Transactional
class RiotCacheApiTest {
    @Autowired MockMvc mvc;
    @Autowired TeamService teams;
    @Autowired JdbcTemplate jdbc;
    @Test void cacheReadsAreIndependentOfRosterAndRequireSavedIdentity() throws Exception {
        var team = teams.create(new TeamData.Create("Riot cache test"));
        String url = "/api/teams/"+team.id()+"/players/BOT/riot";
        mvc.perform(get(url)).andExpect(status().isOk()).andExpect(jsonPath("$.refreshing").value(false)).andExpect(jsonPath("$.profile").doesNotExist());
        mvc.perform(post(url+"/refresh")).andExpect(status().isBadRequest());
        mvc.perform(get("/api/teams/999999/players/BOT/riot")).andExpect(status().isNotFound());
        jdbc.update("update roster_slots set riot_id=? where team_id=? and role=?","Ed#NA1",team.id(),"BOT");
        jdbc.update("insert into riot_profile_cache(riot_id,snapshot) values (?,?::jsonb)","na1:ed#na1",
            "{\"riotId\":\"Ed#NA1\",\"iconUrl\":\"\",\"rank\":null,\"sample\":{\"games\":0,\"champions\":[]},\"requestedMatches\":50,\"updatedAt\":\"2026-09-06T00:00:00Z\"}");
        mvc.perform(get(url)).andExpect(status().isOk()).andExpect(jsonPath("$.profile.riotId").value("Ed#NA1"));
        jdbc.update("update roster_slots set riot_id=? where team_id=? and role=?","SomeoneElse#NA1",team.id(),"BOT");
        mvc.perform(get(url)).andExpect(status().isOk()).andExpect(jsonPath("$.profile").doesNotExist());
    }
}
