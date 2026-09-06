package com.beatrice.backend.team;

import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import static org.springframework.http.HttpStatus.*;
import static com.beatrice.backend.team.TeamData.*;

@Service
public class TeamService {
    private final TeamRepository repository;
    private final com.beatrice.backend.champion.ChampionCatalog catalog;
    public TeamService(TeamRepository repository, com.beatrice.backend.champion.ChampionCatalog catalog) {
        this.repository = repository; this.catalog = catalog;
    }

    @Transactional(readOnly=true, isolation=org.springframework.transaction.annotation.Isolation.REPEATABLE_READ)
    public List<Team> list() { return repository.ids().stream().map(repository::find).toList(); }

    @Transactional(readOnly=true, isolation=org.springframework.transaction.annotation.Isolation.REPEATABLE_READ)
    public Team get(long id) {
        var team = repository.find(id);
        if (team == null) throw new ResponseStatusException(NOT_FOUND, "Team not found.");
        return team;
    }
    @Transactional
    public Team create(Create request) {
        return repository.find(repository.create(cleanName(request.name())));
    }
    @Transactional
    public Team update(long id, Update request) {
        var existing = repository.find(id);
        if (existing == null) throw new ResponseStatusException(NOT_FOUND, "Team not found.");
        var roles = EnumSet.noneOf(Role.class);
        var players = new ArrayList<Player>();
        for (var player : request.players()) {
            if (!roles.add(player.role())) throw new ResponseStatusException(BAD_REQUEST, "Each role must appear exactly once.");
            var names = new HashSet<String>();
            var pool = new ArrayList<Champion>();
            for (var champion : player.champions()) {
                String name = champion.name().strip();
                // Grandfather saved names so legacy typos never destroy a user's existing pool.
                boolean alreadySaved = existing.players().stream().filter(p -> p.role() == player.role())
                    .flatMap(p -> p.champions().stream()).anyMatch(c -> c.name().equalsIgnoreCase(champion.name().strip()));
                if (!alreadySaved) {
                    var official = catalog.findByName(name);
                    if (official == null) throw new ResponseStatusException(BAD_REQUEST, "Choose a champion from the official catalog.");
                    name = official.name();
                }
                if (!names.add(name.toLowerCase(Locale.ROOT))) throw new ResponseStatusException(BAD_REQUEST, "A champion can appear only once per pool.");
                pool.add(new Champion(name, champion.comfort()));
            }
            if (player.name().isBlank() && (!pool.isEmpty() || !player.riotId().isBlank()))
                throw new ResponseStatusException(BAD_REQUEST, "Enter a player name before adding a Riot ID or champion pool.");
            players.add(new Player(player.role(), player.name().strip(), player.riotId().strip(), pool));
        }
        if (!repository.update(id, new Update(cleanName(request.name()), request.version(), players)))
            throw new ResponseStatusException(CONFLICT, "This team changed in another window. Reload teams before saving.");
        return repository.find(id);
    }
    private String cleanName(String name) {
        String clean = name.strip();
        if (clean.isEmpty()) throw new ResponseStatusException(BAD_REQUEST, "Team name is required.");
        return clean;
    }
}
