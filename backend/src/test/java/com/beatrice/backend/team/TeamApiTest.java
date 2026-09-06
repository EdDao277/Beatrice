package com.beatrice.backend.team;

import com.beatrice.backend.TestDatabase;
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
class TeamApiTest {
    @Autowired MockMvc mvc;
    @Autowired TeamService service;
    @Autowired org.springframework.jdbc.core.JdbcTemplate jdbc;

    @Test void preservesUnmatchedLegacyPoolWithoutAllowingNewTypos() throws Exception {
        long id = service.create(new TeamData.Create("Ravens")).id();
        jdbc.update("insert into champion_pools(team_id,role,champion,comfort) values (?,'TOP','Swaim',8)", id);
        mvc.perform(put("/api/teams/" + id).contentType("application/json").content(roster(0, "TOP", 8).replace("Swain", "Swaim")))
            .andExpect(status().isOk()).andExpect(jsonPath("$.players[0].champions[0].name").value("Swaim"));
    }

    private String roster(long version, String topRole, int comfort) {
        return """
            {"name":"Ravens","version":%d,"players":[
              {"role":"%s","name":"Ed","riotId":"Ed#NA1","champions":[{"name":"Swain","comfort":%d}]},
              {"role":"JUNGLE","name":"","riotId":"","champions":[]},
              {"role":"MID","name":"","riotId":"","champions":[]},
              {"role":"BOT","name":"","riotId":"","champions":[]},
              {"role":"SUPPORT","name":"","riotId":"","champions":[]}
            ]}
            """.formatted(version, topRole, comfort);
    }

    @Test
    void rejectsNewMisspelledChampions() throws Exception {
        long id = service.create(new TeamData.Create("Ravens")).id();
        mvc.perform(put("/api/teams/" + id).contentType("application/json").content(roster(0, "TOP", 10).replace("Swain", "Swaim")))
            .andExpect(status().isBadRequest());
    }

    @Test
    void savesRosterAndRejectsStaleEdits() throws Exception {
        long id = service.create(new TeamData.Create("Ravens")).id();
        mvc.perform(put("/api/teams/" + id).contentType("application/json").content(roster(0, "TOP", 10)))
            .andExpect(status().isOk()).andExpect(jsonPath("$.version").value(1))
            .andExpect(jsonPath("$.players[0].champions[0].comfort").value(10));
        mvc.perform(get("/api/teams/" + id)).andExpect(jsonPath("$.players[0].name").value("Ed"));
        mvc.perform(put("/api/teams/" + id).contentType("application/json").content(roster(0, "TOP", 1)))
            .andExpect(status().isConflict());
    }

    @Test
    void rejectsDuplicateRolesAndInvalidComfort() throws Exception {
        long id = service.create(new TeamData.Create("Ravens")).id();
        mvc.perform(put("/api/teams/" + id).contentType("application/json").content(roster(0, "MID", 3)))
            .andExpect(status().isBadRequest());
    }

    @Test
    void rejectsOutOfRangeComfortWithoutChangingRoster() throws Exception {
        long id = service.create(new TeamData.Create("Ravens")).id();
        mvc.perform(put("/api/teams/" + id).contentType("application/json").content(roster(0, "TOP", 11)))
            .andExpect(status().isBadRequest());
        mvc.perform(get("/api/teams/" + id)).andExpect(jsonPath("$.version").value(0))
            .andExpect(jsonPath("$.players[0].champions.length()").value(0));
    }

    @Test
    void createsAndListsTeamWithFiveSlots() throws Exception {
        mvc.perform(post("/api/teams").contentType("application/json").content("{\"name\":\" Ravens \"}"))
            .andExpect(status().isCreated()).andExpect(jsonPath("$.name").value("Ravens"))
            .andExpect(jsonPath("$.players.length()").value(5));
        mvc.perform(get("/api/teams")).andExpect(status().isOk())
            .andExpect(jsonPath("$[0].name").value("Ravens"));
        mvc.perform(post("/api/teams").contentType("application/json").content("{\"name\":\"ravens\"}"))
            .andExpect(status().isConflict());
    }

    @Test
    void rejectsBlankNames() throws Exception {
        mvc.perform(post("/api/teams").contentType("application/json").content("{\"name\":\"  \"}"))
            .andExpect(status().isBadRequest());
    }

    @Test
    void missingTeamReturns404() throws Exception {
        mvc.perform(get("/api/teams/999999")).andExpect(status().isNotFound());
    }
}
