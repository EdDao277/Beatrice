import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchBackendStatus } from "./backendStatus";

describe("fetchBackendStatus", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the backend status response", async () => {
    const fetchMock = vi.fn<typeof fetch>();

    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "UP",
          service: "beatrice-backend",
        }),
        {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        },
      ),
    );

    vi.stubGlobal("fetch", fetchMock);

    const result = await fetchBackendStatus();

    expect(fetchMock).toHaveBeenCalledWith("/api/status");
    expect(result).toEqual({
      status: "UP",
      service: "beatrice-backend",
    });
  });

  it("throws an error when the backend request fails", async () => {
    const fetchMock = vi.fn<typeof fetch>();

    fetchMock.mockResolvedValue(
      new Response(null, {
        status: 503,
      }),
    );

    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchBackendStatus()).rejects.toThrow(
      "Backend status request failed: 503",
    );
  });
});
