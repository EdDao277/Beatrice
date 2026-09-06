package com.beatrice.backend.team;

import java.net.URI;
import java.util.List;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import static com.beatrice.backend.team.TeamData.*;

@RestController
@RequestMapping("/api/teams")
public class TeamController {
    private final TeamService service;
    public TeamController(TeamService service) { this.service = service; }
    @GetMapping public List<Team> list() { return service.list(); }
    @GetMapping("/{id}") public Team get(@PathVariable long id) { return service.get(id); }
    @PostMapping public ResponseEntity<Team> create(@Valid @RequestBody Create request) {
        var team = service.create(request);
        return ResponseEntity.created(URI.create("/api/teams/" + team.id())).body(team);
    }
    @PutMapping("/{id}") public Team update(@PathVariable long id, @Valid @RequestBody Update request) {
        return service.update(id, request);
    }
}

