package com.beatrice.backend.collection;

import java.nio.file.*;
import java.util.concurrent.*;
import jakarta.annotation.PreDestroy;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;
import static org.springframework.http.HttpStatus.*;

/** Local-profile only, fixed configuration path, explicit POST only. No startup crawl. */
@RestController @Profile("local") @RequestMapping("/api/collection")
public class CollectionController {
    private final CollectionCollector collector;
    private final ObjectMapper mapper;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private volatile State state=new State(false,"Not started",null);
    public record State(boolean running,String message,CollectionCollector.Report report) {}
    public CollectionController(CollectionCollector collector,ObjectMapper mapper) {this.collector=collector;this.mapper=mapper;}
    @PreDestroy void stop() {worker.shutdownNow();}
    @GetMapping public State status() {return state;}
    @PostMapping public synchronized State start() {
        if(state.running()) throw new ResponseStatusException(CONFLICT,"Collection already running.");
        CollectionConfig config;
        try {config=mapper.readValue(Files.readString(Path.of("../data/collection/config.json")),CollectionConfig.class);config.validate();}
        catch(Exception e) {throw new ResponseStatusException(BAD_REQUEST,"Check data/collection/config.json: NA routing, seeds, queues, limits, and ISO splitStart.");}
        state=new State(true,"Collecting; saved checkpoints survive interruption.",null);
        worker.submit(()->{
            try {state=new State(false,"Finished",collector.run(config));}
            catch(Exception e) {state=new State(false,e instanceof ResponseStatusException r?r.getReason():"Collection failed; check configuration and metadata availability. Retry resumes saved checkpoints.",null);}
        });
        return state;
    }
}
