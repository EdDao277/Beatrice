package com.beatrice.backend.game;

import java.time.Instant;
import java.util.*;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import com.beatrice.backend.team.TeamData.Team;

public final class GameData {
    private GameData() {}
    public enum Format { RANKED, TOURNAMENT }
    public enum Side { BLUE, RED }
    public enum Kind { BAN, PICK }
    public enum Result { WIN, LOSS }
    public record Assignment(@NotNull Side side, @NotBlank String championId,
        @NotNull com.beatrice.backend.team.TeamData.Role role) {}
    public record AssignmentUpdate(@Min(0) long version,
        @NotNull @Size(max=10) List<@NotNull @Valid Assignment> assignments) {}
    public record Action(@NotNull Kind kind, @NotNull Side side, @Size(max=50) String championId) {}
    public record Create(@NotNull UUID requestId, @NotNull Format format, @NotNull Side side,
        @NotNull Result result, @NotBlank @Size(max=30) String patch,
        @NotNull @Size(min=20, max=20) List<@NotNull @Valid Action> actions) {}
    public record Game(long id, long teamId, Format format, Side side, Result result, String patch,
        List<Action> actions, Team roster, Map<String, String> championNames, Instant recordedAt,
        List<Assignment> assignments, long assignmentVersion) {}
}
