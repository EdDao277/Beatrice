package com.beatrice.backend.game;

import java.util.List;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import static com.beatrice.backend.game.GameData.*;

@RestController
@RequestMapping("/api/teams/{teamId}/games")
public class GameController {
    private final GameService service;
    public GameController(GameService service) { this.service=service; }
    @PutMapping("/{id}/assignments")
    public Game assign(@PathVariable long teamId, @PathVariable long id,
            @Valid @RequestBody AssignmentUpdate request) { return service.assign(teamId, id, request); }
    @GetMapping public List<Game> list(@PathVariable long teamId) { return service.list(teamId); }
    @PostMapping @ResponseStatus(HttpStatus.CREATED)
    public Game create(@PathVariable long teamId, @Valid @RequestBody Create request) { return service.create(teamId, request); }
}
