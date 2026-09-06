import { render, screen, cleanup } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  localStorage.clear();
});

it("creates a team through the API and displays five roster slots", async () => {
  const players = ["TOP", "JUNGLE", "MID", "BOT", "SUPPORT"].map((role) => ({
    role,
    name: "",
    riotId: "",
    champions: [],
  }));
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(new Response("[]"))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ id: 1, name: "Ravens", version: 0, players }),
        ),
      ),
  );
  render(<App />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Create your first team" }),
  );
  await userEvent.type(screen.getByLabelText("New team name"), "Ravens");
  await userEvent.click(screen.getByRole("button", { name: "Create team" }));
  expect(
    await screen.findByRole("heading", { name: "Ravens" }),
  ).toBeInTheDocument();
  expect(screen.getAllByLabelText("Player name")).toHaveLength(5);
});

it("shows a recoverable connection error", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(/connect/i);
  expect(
    screen.getByRole("button", { name: "Retry connection" }),
  ).toBeInTheDocument();
});
