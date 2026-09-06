package com.beatrice.backend.champion;

import java.nio.file.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import tools.jackson.databind.json.JsonMapper;
import org.springframework.web.server.ResponseStatusException;
import static org.junit.jupiter.api.Assertions.*;

class ChampionCatalogTest {
    @TempDir Path root;
    @Test void readsOfficialNamesAndOnlyServesCatalogImages() throws Exception {
        Files.createDirectories(root.resolve("data/en_US"));
        Files.createDirectories(root.resolve("img/champion"));
        Files.writeString(root.resolve("data/en_US/champion.json"), """
            {"version":"test","data":{"MonkeyKing":{"id":"MonkeyKing","name":"Wukong","image":{"full":"MonkeyKing.png"}}}}
            """);
        Files.write(root.resolve("img/champion/MonkeyKing.png"), new byte[]{1, 2, 3});
        var catalog = new ChampionCatalog(root.toString(), JsonMapper.builder().build());
        assertEquals("Wukong", catalog.catalog().champions().getFirst().name());
        assertEquals("MonkeyKing", catalog.findByName(" wUkOnG ").id());
        assertTrue(catalog.portrait("MonkeyKing").exists());
        assertThrows(ResponseStatusException.class, () -> catalog.portrait("../champion.json"));
    }
    @Test void missingCatalogHasActionableError() {
        var catalog = new ChampionCatalog(root.toString(), JsonMapper.builder().build());
        var error = assertThrows(ResponseStatusException.class, catalog::catalog);
        assertEquals(503, error.getStatusCode().value());
    }
}
