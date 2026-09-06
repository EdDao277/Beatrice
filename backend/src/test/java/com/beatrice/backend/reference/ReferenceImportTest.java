package com.beatrice.backend.reference;

import com.beatrice.backend.TestDatabase;
import java.nio.file.*;
import java.util.zip.GZIPOutputStream;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest @Import(TestDatabase.class) @Transactional
class ReferenceImportTest {
    @Autowired ReferenceImporter importer;
    @Autowired JdbcTemplate jdbc;
    @Autowired ReferenceService service;
    @TempDir Path temp;
    @Test void importsReferenceOnlyNormalizesRolesAndIsIdempotent() throws Exception {
        Path file = temp.resolve("reference.gz");
        try (var out = new GZIPOutputStream(Files.newOutputStream(file))) { out.write(("""
            DROP TABLE teams;
            COPY public.teams (name) FROM stdin;
            Do not import me
            \\.
            COPY public.champion_metadata (champion_id, roles, damage_type) FROM stdin;
            swain\t{Mid,Support,ADC}\tmagic
            \\.
            COPY public.champion_role_stats (patch, region, queue_id, source_type, champion_id, role, games, wins, confidence) FROM stdin;
            16.15\tamericas\t420\tgeneral-network\tSwain\tADC\t20\t12\t0.35
            \\.
            COPY public.champion_synergy_stats (patch, region, queue_id, source_type, champion_id, role, ally_champion_id, ally_role, games, wins, delta_vs_average, confidence) FROM stdin;
            16.15\tamericas\t420\tgeneral-network\tSwain\tADC\tC0\tSupport\t5\t4\t0.2\t0.15
            16.15\tamericas\t420\tgeneral-network\tC0\tSupport\tSwain\tADC\t5\t4\t0.2\t0.15
            16.15\tamericas\t440\tgeneral-network\tSwain\tADC\tC0\tSupport\t8\t2\t-0.1\t0.15
            \\.
            """).getBytes(java.nio.charset.StandardCharsets.UTF_8)); }
        long teamsBefore = jdbc.queryForObject("select count(*) from teams", Long.class);
        var first=importer.importFile(file);
        assertEquals(first.id(), importer.importFile(file).id());
        assertEquals(teamsBefore, jdbc.queryForObject("select count(*) from teams", Long.class));
        assertEquals(1, jdbc.queryForObject("select count(*) from reference_imports", Integer.class));
        var data = service.evidence("Swain", "16.15", 420, "americas", "general-network", "BOT");
        assertEquals(java.util.List.of("MID","SUPPORT","BOT"), data.roles());
        assertEquals(1, data.synergies().size());
        assertEquals(5, data.synergies().getFirst().games());
        assertEquals(0.8, data.synergies().getFirst().winRate());
        assertTrue(service.evidence("Swain", "16.17", 420, "americas", "general-network", "BOT").synergies().isEmpty());
    }
}
