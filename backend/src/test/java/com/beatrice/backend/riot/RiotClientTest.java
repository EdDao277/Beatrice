package com.beatrice.backend.riot;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;
import static org.junit.jupiter.api.Assertions.*;
class RiotClientTest {
    @Test void encodesUserInputAsOnePathSegment() {
        assertEquals("Name%20%2F%23%3F", RiotClient.segment("Name /#?"));
    }
    @Test void explainsAuthAndRateErrorsWithoutUpstreamBody() {
        assertTrue(assertThrows(ResponseStatusException.class, () -> RiotClient.checkStatus(403)).getReason().contains("API key"));
        assertEquals(429, assertThrows(ResponseStatusException.class, () -> RiotClient.checkStatus(429)).getStatusCode().value());
        assertDoesNotThrow(() -> RiotClient.checkStatus(200));
    }
    @Test void missingKeyFailsBeforeNetworkRequest() {
        var client = new RiotClient("",new ObjectMapper());
        assertEquals(503, assertThrows(ResponseStatusException.class, () -> client.get(true,"/unused")).getStatusCode().value());
    }
}
