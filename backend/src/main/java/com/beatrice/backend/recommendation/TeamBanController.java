package com.beatrice.backend.recommendation;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import static org.springframework.http.HttpStatus.BAD_REQUEST;

@RestController
public class TeamBanController {
    private final TeamBanService service;
    public TeamBanController(TeamBanService service) {this.service=service;}
    @PostMapping("/api/teams/{teamId}/draft/bans")
    public TeamBanService.Response recommend(@PathVariable long teamId,@Valid @RequestBody TeamBanService.Request request) {
        try {return service.recommend(teamId,request);}
        catch(IllegalArgumentException error) {throw new ResponseStatusException(BAD_REQUEST,"Invalid ban context.");}
    }
}
