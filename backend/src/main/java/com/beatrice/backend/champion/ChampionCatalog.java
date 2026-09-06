package com.beatrice.backend.champion;

import java.nio.file.*;
import java.io.IOException;
import java.util.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;
import static org.springframework.http.HttpStatus.*;

/** Read only the configured patch. No remote calls, credentials, or arbitrary file serving. */
@Service
public class ChampionCatalog {
    public record Champion(String id, String name, String portrait) {}
    public record Catalog(String version, List<Champion> champions) {}
    private final Path root;
    private final ObjectMapper mapper;
    private Catalog cached;
    private Map<String, Path> images = Map.of();
    public ChampionCatalog(@Value("${beatrice.ddragon.path:../data/ddragon/extracted/16.17.1}") String path, ObjectMapper mapper) {
        this.root = Path.of(path).toAbsolutePath().normalize();
        this.mapper = mapper;
    }
    public synchronized Catalog catalog() {
        if (cached != null) return cached;
        try (var input = Files.newInputStream(root.resolve("data/en_US/champion.json"))) {
            var json = mapper.readTree(input);
            var champions = new ArrayList<Champion>();
            var paths = new HashMap<String, Path>();
            for (var node : json.path("data")) {
                String id = node.path("id").asString();
                String name = node.path("name").asString();
                String file = node.path("image").path("full").asString();
                if (!id.matches("[A-Za-z0-9]+") || !file.matches("[A-Za-z0-9]+\\.png") || name.isBlank())
                    throw new IOException("Invalid catalog entry");
                champions.add(new Champion(id, name, "/api/champions/" + id + "/portrait"));
                paths.put(id, root.resolve("img/champion").resolve(file));
            }
            if (champions.isEmpty() || json.path("version").asString().isBlank()) throw new IOException("Empty catalog");
            champions.sort(Comparator.comparing(Champion::name));
            images = Map.copyOf(paths);
            cached = new Catalog(json.path("version").asString(), List.copyOf(champions));
            return cached;
        } catch (IOException | RuntimeException error) {
            throw new ResponseStatusException(SERVICE_UNAVAILABLE,
                "Champion data is unavailable. Extract data/en_US and img/champion, check beatrice.ddragon.path, then retry.");
        }
    }
    public Champion findByName(String name) {
        return catalog().champions().stream().filter(c -> c.name().equalsIgnoreCase(name.strip())).findFirst().orElse(null);
    }
    public Champion require(String id) {
        return catalog().champions().stream().filter(c -> c.id().equals(id)).findFirst()
            .orElseThrow(() -> new ResponseStatusException(BAD_REQUEST, "Unknown champion selection."));
    }
    public FileSystemResource portrait(String id) {
        catalog();
        Path path = images.get(id);
        if (path == null || !Files.isRegularFile(path)) throw new ResponseStatusException(NOT_FOUND, "Champion portrait not found.");
        return new FileSystemResource(path);
    }
}
