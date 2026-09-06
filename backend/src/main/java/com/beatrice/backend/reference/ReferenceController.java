package com.beatrice.backend.reference;

import org.springframework.web.bind.annotation.*;
import com.beatrice.backend.champion.ChampionCatalog;

@RestController @RequestMapping("/api/reference")
public class ReferenceController {
    private final ReferenceService service; private final ChampionCatalog catalog;
    public ReferenceController(ReferenceService service,ChampionCatalog catalog) {this.service=service;this.catalog=catalog;}
    @GetMapping("/options") public ReferenceService.Options options() {return service.options();}
    @GetMapping("/champions/{id}") public ReferenceService.Evidence evidence(@PathVariable String id,
        @RequestParam String patch,@RequestParam int queueId,@RequestParam String region,@RequestParam String source,@RequestParam String role) {
        catalog.require(id);
        return service.evidence(id,patch,queueId,region,source,role);
    }
}
