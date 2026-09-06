package com.beatrice.backend;

import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.context.annotation.Bean;
import org.testcontainers.postgresql.PostgreSQLContainer;

/** Tests use a disposable database, never the user's saved teams. */
@TestConfiguration(proxyBeanMethods = false)
public class TestDatabase {
    @Bean
    @org.springframework.context.annotation.Primary
    com.beatrice.backend.champion.ChampionCatalog testCatalog(tools.jackson.databind.ObjectMapper mapper) throws java.io.IOException {
        // Small local fixture: tests never depend on the user's multi-gigabyte download.
        var root = java.nio.file.Files.createTempDirectory("beatrice-test-catalog-");
        java.nio.file.Files.createDirectories(root.resolve("data/en_US"));
        var entries = new java.util.ArrayList<String>();
        for (int i=0; i<20; i++) entries.add("\"C%d\":{\"id\":\"C%d\",\"name\":\"Champion %d\",\"image\":{\"full\":\"C%d.png\"}}".formatted(i,i,i,i));
        entries.add("\"Swain\":{\"id\":\"Swain\",\"name\":\"Swain\",\"image\":{\"full\":\"Swain.png\"}}");
        java.nio.file.Files.writeString(root.resolve("data/en_US/champion.json"), "{\"version\":\"test\",\"data\":{" + String.join(",", entries) + "}}");
        return new com.beatrice.backend.champion.ChampionCatalog(root.toString(), mapper);
    }
    @Bean
    @ServiceConnection
    PostgreSQLContainer postgres() {
        return new PostgreSQLContainer("postgres:17");
    }
}
