package com.beatrice.backend.riot;

import org.springframework.web.bind.annotation.*;
import com.beatrice.backend.team.TeamData.Role;

@RestController
@RequestMapping("/api/teams/{teamId}/players/{role}/riot")
public class RiotController {
    private final RiotProfiles profiles;
    public RiotController(RiotProfiles profiles) { this.profiles=profiles; }
    @GetMapping public RiotProfiles.State get(@PathVariable long teamId,@PathVariable Role role) { return profiles.get(teamId,role); }
    @PostMapping("/refresh") @ResponseStatus(org.springframework.http.HttpStatus.ACCEPTED)
    public RiotProfiles.State refresh(@PathVariable long teamId,@PathVariable Role role) { return profiles.refresh(teamId,role); }
}
