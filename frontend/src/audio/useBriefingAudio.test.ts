import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Briefing, TeamId } from "../api/types";
import { useBriefingAudio } from "./useBriefingAudio";

function fakeBriefing(overrides: Partial<Briefing> = {}): Briefing {
  return {
    briefing_id: "decision_blue_1",
    match_id: "match_001",
    team_id: "blue",
    coach_id: "coach_blue",
    coach_name: "Blue Coach",
    transcript: "We found space down the left.",
    audio_status: "ready",
    audio_url: "/audio/decision_blue_1.mp3",
    ...overrides,
  };
}

function fakeAudioElement() {
  return {
    play: vi.fn().mockResolvedValue(undefined),
    pause: vi.fn(),
    addEventListener: vi.fn(),
    currentTime: 0,
  };
}

type FakeAudio = ReturnType<typeof fakeAudioElement>;

function setupDeps(briefingsByTeam: Partial<Record<TeamId, Briefing>>) {
  const createdAudios: FakeAudio[] = [];
  const getBriefing = vi.fn(async (_matchId: string, teamId: TeamId) => {
    const briefing = briefingsByTeam[teamId];
    if (!briefing) throw new Error("not found");
    return briefing;
  });
  const createAudio = vi.fn((_src: string) => {
    const audio = fakeAudioElement();
    createdAudios.push(audio);
    return audio as unknown as HTMLAudioElement;
  });
  return { deps: { getBriefing, createAudio }, createdAudios, getBriefing };
}

describe("useBriefingAudio", () => {
  it("fetches the briefing via a read-only call and plays its audio", async () => {
    const blue = fakeBriefing();
    const { deps, getBriefing, createdAudios } = setupDeps({ blue });

    const { result } = renderHook(() => useBriefingAudio("match_001", "blue", deps));

    await waitFor(() => expect(result.current.status).toBe("playing"));

    expect(getBriefing).toHaveBeenCalledOnce();
    expect(getBriefing).toHaveBeenCalledWith("match_001", "blue");
    expect(createdAudios[0]!.play).toHaveBeenCalledOnce();
  });

  it("stops the previous team's audio immediately when switching teams", async () => {
    const blue = fakeBriefing({ team_id: "blue", briefing_id: "d_blue" });
    const red = fakeBriefing({ team_id: "red", briefing_id: "d_red", audio_url: "/audio/d_red.mp3" });
    const { deps, createdAudios } = setupDeps({ blue, red });

    const { result, rerender } = renderHook<ReturnType<typeof useBriefingAudio>, { team: TeamId | null }>(
      ({ team }) => useBriefingAudio("match_001", team, deps),
      { initialProps: { team: "blue" } },
    );
    await waitFor(() => expect(result.current.status).toBe("playing"));
    const blueAudio = createdAudios[0]!;

    rerender({ team: "red" });
    await waitFor(() => expect(result.current.status).toBe("playing"));

    expect(blueAudio.pause).toHaveBeenCalled();
    expect(createdAudios).toHaveLength(2);
  });

  it("never has two audio elements playing: the previous one is paused before the next starts", async () => {
    const blue = fakeBriefing({ team_id: "blue" });
    const red = fakeBriefing({ team_id: "red", audio_url: "/audio/red.mp3" });
    const { deps, createdAudios } = setupDeps({ blue, red });

    const { rerender } = renderHook<ReturnType<typeof useBriefingAudio>, { team: TeamId | null }>(
      ({ team }) => useBriefingAudio("match_001", team, deps),
      { initialProps: { team: "blue" } },
    );
    await waitFor(() => expect(createdAudios).toHaveLength(1));

    act(() => rerender({ team: "red" }));
    await waitFor(() => expect(createdAudios).toHaveLength(2));

    const stillPlaying = createdAudios.filter((audio) => audio.pause.mock.calls.length === 0);
    expect(stillPlaying.length).toBeLessThanOrEqual(1);
  });

  it("marks audio unavailable without creating an audio element when the backend has none ready", async () => {
    const blue = fakeBriefing({ audio_status: "unavailable", audio_url: null });
    const { deps, createdAudios } = setupDeps({ blue });

    const { result } = renderHook(() => useBriefingAudio("match_001", "blue", deps));

    await waitFor(() => expect(result.current.status).toBe("unavailable"));
    expect(createdAudios).toHaveLength(0);
  });

  it("caches the briefing per match/team so re-selecting doesn't refetch", async () => {
    const blue = fakeBriefing();
    const { deps, getBriefing } = setupDeps({ blue });

    const { rerender } = renderHook<ReturnType<typeof useBriefingAudio>, { team: TeamId | null }>(
      ({ team }) => useBriefingAudio("match_001", team, deps),
      { initialProps: { team: "blue" } },
    );
    await waitFor(() => expect(getBriefing).toHaveBeenCalledOnce());

    rerender({ team: null });
    rerender({ team: "blue" });

    await waitFor(() => expect(getBriefing).toHaveBeenCalledOnce());
  });

  it("deselecting stops audio and returns to idle", async () => {
    const blue = fakeBriefing();
    const { deps, createdAudios } = setupDeps({ blue });

    const { result, rerender } = renderHook<ReturnType<typeof useBriefingAudio>, { team: TeamId | null }>(
      ({ team }) => useBriefingAudio("match_001", team, deps),
      { initialProps: { team: "blue" } },
    );
    await waitFor(() => expect(result.current.status).toBe("playing"));

    rerender({ team: null });

    expect(result.current.status).toBe("idle");
    expect(createdAudios[0]!.pause).toHaveBeenCalled();
  });
});
