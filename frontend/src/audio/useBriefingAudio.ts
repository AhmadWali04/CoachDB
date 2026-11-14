import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Briefing, TeamId } from "../api/types";

export type PlaybackStatus = "idle" | "loading" | "playing" | "paused" | "unavailable" | "error";

export interface BriefingAudioDeps {
  getBriefing: (matchId: string, teamId: TeamId) => Promise<Briefing>;
  createAudio: (src: string) => HTMLAudioElement;
}

const defaultDeps: BriefingAudioDeps = {
  getBriefing: (matchId, teamId) => api.getBriefing(matchId, teamId),
  createAudio: (src) => new Audio(src),
};

export interface BriefingAudioState {
  status: PlaybackStatus;
  briefing: Briefing | null;
  play: () => void;
  pause: () => void;
  replay: () => void;
}

function attemptPlay(audio: HTMLAudioElement, onSuccess: () => void, onFailure: () => void): void {
  let result: unknown;
  try {
    result = audio.play();
  } catch {
    onFailure();
    return;
  }
  if (result && typeof (result as Promise<void>).then === "function") {
    (result as Promise<void>).then(onSuccess).catch(onFailure);
  } else {
    onSuccess();
  }
}

/** Fetches (read-only) and plays a coach's approved halftime briefing.
 * Selecting a team never writes to the API and never regenerates audio
 * that's already loaded; switching teams always stops the previous clip
 * first, so at most one briefing plays at a time (PRD §13.3). */
export function useBriefingAudio(
  matchId: string | null,
  selectedTeam: TeamId | null,
  deps: BriefingAudioDeps = defaultDeps,
): BriefingAudioState {
  const [status, setStatus] = useState<PlaybackStatus>("idle");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cacheRef = useRef<Map<string, Briefing>>(new Map());

  const stopCurrentAudio = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    audioRef.current = null;
  }, []);

  const setupAudio = useCallback(
    (result: Briefing) => {
      if (result.audio_status !== "ready" || !result.audio_url) {
        setStatus("unavailable");
        return;
      }
      const audio = deps.createAudio(result.audio_url);
      audio.addEventListener("ended", () => setStatus("paused"));
      audioRef.current = audio;
      attemptPlay(
        audio,
        () => setStatus("playing"),
        () => setStatus("unavailable"),
      );
    },
    [deps],
  );

  useEffect(() => {
    stopCurrentAudio();
    setBriefing(null);

    if (!matchId || !selectedTeam) {
      setStatus("idle");
      return;
    }

    const cacheKey = `${matchId}:${selectedTeam}`;
    const cached = cacheRef.current.get(cacheKey);
    if (cached) {
      setBriefing(cached);
      setupAudio(cached);
      return;
    }

    let cancelled = false;
    setStatus("loading");
    deps
      .getBriefing(matchId, selectedTeam)
      .then((result) => {
        if (cancelled) return;
        cacheRef.current.set(cacheKey, result);
        setBriefing(result);
        setupAudio(result);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 404) {
          setStatus("unavailable");
        } else {
          setStatus("error");
        }
      });

    return () => {
      cancelled = true;
    };
    // stopCurrentAudio/setupAudio are stable for the lifetime of `deps`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [matchId, selectedTeam, deps]);

  useEffect(() => stopCurrentAudio, [stopCurrentAudio]);

  const play = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    attemptPlay(
      audio,
      () => setStatus("playing"),
      () => setStatus("unavailable"),
    );
  }, []);

  const pause = useCallback(() => {
    audioRef.current?.pause();
    setStatus("paused");
  }, []);

  const replay = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = 0;
    attemptPlay(
      audio,
      () => setStatus("playing"),
      () => setStatus("unavailable"),
    );
  }, []);

  return { status, briefing, play, pause, replay };
}
