package com.beatrice.backend.riot;

import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.*;
import static org.springframework.http.HttpStatus.*;

/** Fixed upstream hosts and token header only: no arbitrary URL proxy or credential logging. */
@Component
public class RiotClient {
    private final String key;
    private final ObjectMapper mapper;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
    private long nextCall;
    public RiotClient(@Value("${RIOT_API_KEY:}") String key, ObjectMapper mapper) { this.key=key.strip(); this.mapper=mapper; }
    public static String segment(String value) { return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20"); }
    public synchronized JsonNode get(boolean regional, String path) {
        if (key.isBlank()) throw new ResponseStatusException(SERVICE_UNAVAILABLE, "Add RIOT_API_KEY to the root .env and restart the backend.");
        long wait = nextCall - System.currentTimeMillis();
        if (wait > 5000) throw new ResponseStatusException(TOO_MANY_REQUESTS, "Riot rate limit reached. Wait a few minutes before refreshing.");
        try {
            // A single worker plus conservative pacing stays below standard development-key limits.
            if (wait > 0) Thread.sleep(wait);
            nextCall = System.currentTimeMillis() + 1300;
            var request = HttpRequest.newBuilder(URI.create("https://" + (regional ? "americas" : "na1") + ".api.riotgames.com" + path))
                .timeout(Duration.ofSeconds(20)).header("X-Riot-Token", key).GET().build();
            var response = http.send(request, HttpResponse.BodyHandlers.ofString());
            int status = response.statusCode();
            if (status == 429) {
                long seconds = 120;
                try { seconds = Math.max(1, Long.parseLong(response.headers().firstValue("Retry-After").orElse("120"))); } catch (NumberFormatException ignored) { }
                nextCall = System.currentTimeMillis() + Math.min(seconds, 86400) * 1000;
            }
            checkStatus(status);
            return mapper.readTree(response.body());
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(SERVICE_UNAVAILABLE, "Riot refresh interrupted. Please retry.");
        } catch (java.io.IOException error) {
            throw new ResponseStatusException(SERVICE_UNAVAILABLE, "Riot could not be reached. Please retry later.");
        }
    }
    static void checkStatus(int status) {
        if (status == 200) return;
        String message = switch(status) {
            case 401, 403 -> "Riot rejected the API key. Check whether it expired, update .env, and restart the backend.";
            case 404 -> "Riot account or data not found on NA. Check the saved Name#Tag.";
            case 429 -> "Riot rate limit reached. Wait before refreshing again.";
            default -> "Riot data is temporarily unavailable. Please retry later.";
        };
        throw new ResponseStatusException(status == 429 ? TOO_MANY_REQUESTS : BAD_GATEWAY, message);
    }
}
