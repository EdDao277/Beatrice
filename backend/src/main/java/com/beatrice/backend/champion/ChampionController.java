package com.beatrice.backend.champion;

import org.springframework.core.io.Resource;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/champions")
public class ChampionController {
    private final ChampionCatalog catalog;
    public ChampionController(ChampionCatalog catalog) { this.catalog = catalog; }
    @GetMapping public ChampionCatalog.Catalog list() { return catalog.catalog(); }
    @GetMapping(value="/{id}/portrait", produces=MediaType.IMAGE_PNG_VALUE)
    public ResponseEntity<Resource> portrait(@PathVariable String id) {
        return ResponseEntity.ok().cacheControl(CacheControl.noCache()).body(catalog.portrait(id));
    }
}
