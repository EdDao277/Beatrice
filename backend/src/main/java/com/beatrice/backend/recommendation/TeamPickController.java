package com.beatrice.backend.recommendation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.web.bind.annotation.*;

@RestController
public class TeamPickController {
    private final TeamPickService service;
    private final PickDiagnostics diagnostics;
    public TeamPickController(TeamPickService service,PickDiagnostics diagnostics) {this.service=service;this.diagnostics=diagnostics;}
    @PostMapping("/api/teams/{teamId}/draft/picks")
    public TeamPickService.Response picks(@PathVariable long teamId,@Valid @RequestBody TeamPickService.Request request) {
        return service.recommend(teamId,request);
    }
    public record Selection(@NotBlank @Size(max=40) String requestId,@NotBlank @Size(max=50) String championId) {}
    @PostMapping("/api/teams/{teamId}/draft/picks/selected")
    @ResponseStatus(org.springframework.http.HttpStatus.NO_CONTENT)
    public void selected(@PathVariable long teamId,@Valid @RequestBody Selection selection) {
        diagnostics.selected(selection.requestId(),teamId,selection.championId());
    }
}
