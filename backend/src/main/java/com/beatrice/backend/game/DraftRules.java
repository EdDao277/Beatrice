package com.beatrice.backend.game;

import java.util.*;
import com.beatrice.backend.champion.ChampionCatalog;
import org.springframework.web.server.ResponseStatusException;
import static org.springframework.http.HttpStatus.BAD_REQUEST;
import static com.beatrice.backend.game.GameData.*;

/** Server validation is independent of the browser: a crafted request cannot bypass rules. */
public final class DraftRules {
    private DraftRules() {}
    private static final String[] TOURNAMENT = "BLUE RED BLUE RED BLUE RED BLUE RED RED BLUE BLUE RED RED BLUE RED BLUE RED BLUE BLUE RED".split(" ");
    private static final String[] PICKS = "BLUE RED RED BLUE BLUE RED RED BLUE BLUE RED".split(" ");
    public static void validate(Create request, ChampionCatalog catalog) {
        if (!catalog.catalog().version().equals(request.patch())) fail("The champion patch changed. Start a new draft with the current catalog.");
        if (request.actions().size() != 20) fail("Complete the draft before recording a result.");
        validatePrefix(request.format(),request.actions(),catalog);
    }
    public static void validatePrefix(Format format,List<Action> actions,ChampionCatalog catalog) {
        if(format==null || actions==null || actions.size()>20) fail("Invalid draft state.");
        var used = new HashSet<String>();
        var blueBans = new HashSet<String>();
        var redBans = new HashSet<String>();
        int blueCount=0, redCount=0;
        for (int n=0; n<actions.size(); n++) {
            var a = actions.get(n);
            if(a==null || a.kind()==null || a.side()==null) fail("Invalid draft action.");
            boolean ranked = format == Format.RANKED;
            boolean ban = ranked ? n < 10 : n < 6 || (n >= 12 && n < 16);
            if (a.kind() != (ban ? Kind.BAN : Kind.PICK)) fail("Invalid pick / ban phase.");
            if (!(ranked && ban)) {
                String expected = ranked ? PICKS[n-10] : TOURNAMENT[n];
                if (!a.side().name().equals(expected)) fail("Invalid draft turn order.");
            } else {
                if (a.side() == Side.BLUE) blueCount++; else redCount++;
                if (blueCount > 5 || redCount > 5) fail("Each side has five ban slots.");
            }
            String id = a.championId();
            if (id == null) { if (!ban) fail("A pick must have a champion."); continue; }
            catalog.require(id);
            // Opposing duplicate bans are legitimate only during simultaneous ranked bans.
            if (ranked && ban) {
                if (!(a.side() == Side.BLUE ? blueBans : redBans).add(id)) fail("Duplicate ban on one team.");
                used.add(id);
            } else if (!used.add(id)) fail("A selected champion is already picked or banned.");
        }
    }
    private static void fail(String message) { throw new ResponseStatusException(BAD_REQUEST, message); }
}
