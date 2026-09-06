package com.beatrice.backend.team;

import java.util.List;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;

/** API records keep our JSON contract independent of database rows. */
public final class TeamData {
    private TeamData() {}
    public enum Role { TOP, JUNGLE, MID, BOT, SUPPORT }
    public record Champion(@NotBlank @Size(max=50) String name,
                           @Min(1) @Max(10) int comfort) {}
    public record Player(@NotNull Role role, @NotNull @Size(max=80) String name,
                         @NotNull @Size(max=100) String riotId,
                         @NotNull @Size(max=100) List<@NotNull @Valid Champion> champions) {}
    public record Create(@NotBlank @Size(max=80) String name) {}
    public record Update(@NotBlank @Size(max=80) String name, @Min(0) long version,
                         @NotNull @Size(min=5, max=5) List<@NotNull @Valid Player> players) {}
    public record Team(long id, String name, long version, List<Player> players) {}
}
