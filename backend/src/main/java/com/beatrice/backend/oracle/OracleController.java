package com.beatrice.backend.oracle;

import java.nio.file.*;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import static org.springframework.http.HttpStatus.BAD_REQUEST;

/** No automatic import; only a named local batch under data/oracle can be opened. */
@RestController @Profile("local") @RequestMapping("/api/oracle")
public class OracleController {
    private final OracleImporter importer;
    public OracleController(OracleImporter importer) {this.importer=importer;}
    @PostMapping("/imports/{batch}") public OracleImporter.Report importBatch(@PathVariable String batch) throws Exception {
        if(!batch.matches("prepared[-a-zA-Z0-9_]*")) throw new ResponseStatusException(BAD_REQUEST,"Select a prepared batch folder.");
        try {
            Path root=Path.of("../data/oracle").toRealPath(), folder=root.resolve(batch).toRealPath();
            if(!folder.startsWith(root)) throw new IllegalArgumentException("Invalid batch folder.");
            for(String file:java.util.List.of("games.jsonl","report.json")) if(!folder.resolve(file).toRealPath().startsWith(folder)) throw new IllegalArgumentException("Invalid batch file.");
            return importer.importBatch(folder);
        } catch(IllegalArgumentException | java.io.IOException error) {
            throw new ResponseStatusException(BAD_REQUEST,"Oracle import rejected: "+error.getMessage());
        }
    }
}
