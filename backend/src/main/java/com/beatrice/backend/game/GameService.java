package com.beatrice.backend.game;

import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import com.beatrice.backend.champion.ChampionCatalog;
import com.beatrice.backend.team.TeamService;
import static org.springframework.http.HttpStatus.CONFLICT;
import static com.beatrice.backend.game.GameData.*;

@Service
public class GameService {
    private final GameRepository repository;
    private final TeamService teams;
    private final ChampionCatalog catalog;
    public GameService(GameRepository repository, TeamService teams, ChampionCatalog catalog) {
        this.repository=repository; this.teams=teams; this.catalog=catalog;
    }
    @Transactional(readOnly=true)
    public List<Game> list(long teamId) { teams.get(teamId); return repository.list(teamId); }
    @Transactional
    public Game assign(long teamId, long id, AssignmentUpdate request) {
        var game = list(teamId).stream().filter(item -> item.id()==id).findFirst()
            .orElseThrow(() -> new ResponseStatusException(org.springframework.http.HttpStatus.NOT_FOUND, "Game not found."));
        var champions = new java.util.HashSet<String>();
        var roles = new java.util.HashSet<String>();
        for (var assignment : request.assignments()) {
            boolean picked = game.actions().stream().anyMatch(action -> action.kind()==Kind.PICK
                && action.side()==assignment.side() && assignment.championId().equals(action.championId()));
            if (!picked || !champions.add(assignment.side()+":"+assignment.championId())
                    || !roles.add(assignment.side()+":"+assignment.role()))
                throw new ResponseStatusException(org.springframework.http.HttpStatus.BAD_REQUEST,
                    "Assign only that side's picks, with one champion per role. Leave uncertain roles unassigned.");
        }
        if (!repository.updateAssignments(teamId, id, request))
            throw new ResponseStatusException(CONFLICT, "This lineup changed in another tab. Reload history before saving.");
        return repository.list(teamId).stream().filter(item -> item.id()==id).findFirst().orElseThrow();
    }
    @Transactional
    public Game create(long teamId, Create request) {
        repository.lockTeamSnapshot(teamId);
        var team = teams.get(teamId);
        if (repository.existingId(request.requestId()) == null) {
            DraftRules.validate(request, catalog);
            var names = new java.util.HashMap<String, String>();
            for (var action : request.actions()) if (action.championId() != null)
                names.put(action.championId(), catalog.require(action.championId()).name());
            repository.insert(teamId, request, team, names);
        }
        if (!repository.sameRequest(teamId, request))
            throw new ResponseStatusException(CONFLICT, "This recording ID was already used with different data. Start a new draft.");
        long id = repository.existingId(request.requestId());
        return repository.list(teamId).stream().filter(game -> game.id() == id).findFirst().orElseThrow();
    }
}
