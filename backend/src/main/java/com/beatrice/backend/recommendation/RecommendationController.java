package com.beatrice.backend.recommendation;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import java.util.List;
import static org.springframework.http.HttpStatus.BAD_REQUEST;
@RestController
public class RecommendationController {
    private final RecommendationService service;
    public RecommendationController(RecommendationService service) {this.service=service;}
    @GetMapping("/api/recommendations/datasets") public List<RecommendationService.Dataset> datasets() {return service.datasets();}
    @PostMapping("/api/teams/{teamId}/draft/recommendations")
    public RecommendationService.Response recommend(@PathVariable long teamId,@Valid @RequestBody RecommendationService.Request request) {
        try {return service.recommend(teamId,request);} catch(IllegalArgumentException e) {throw new ResponseStatusException(BAD_REQUEST,"Invalid recommendation context.");}
    }
}
