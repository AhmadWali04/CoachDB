import { useEffect, useRef, useState } from "react";
import type { BallPosition, Frame, PlayerPosition } from "../api/types";
import { interpolateBall, interpolatePlayers } from "./playback";

const STEP_DURATION_MS = 1500;

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export interface FramePlayback {
  currentFrame: Frame | null;
  players: PlayerPosition[];
  ball: BallPosition | null;
  index: number;
  isPlaying: boolean;
  play: () => void;
  pause: () => void;
  seek: (index: number) => void;
}

/** Plays recorded/live frames at a fixed cadence, interpolating player and
 * ball positions between consecutive frames. Never advances past the
 * frames it was given -- it visualizes simulation output, it doesn't
 * generate any (PRD §13.2). */
export function useFramePlayback(frames: Frame[]): FramePlayback {
  const [index, setIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [, forceRender] = useState(0);
  const reducedMotion = prefersReducedMotion();
  const stepStartedAt = useRef(0);
  const rafId = useRef<number | undefined>(undefined);

  useEffect(() => {
    setIndex(0);
  }, [frames]);

  useEffect(() => {
    if (!isPlaying || frames.length < 2) return;
    stepStartedAt.current = performance.now();

    const tick = (now: number) => {
      const elapsed = now - stepStartedAt.current;
      if (elapsed >= STEP_DURATION_MS) {
        stepStartedAt.current = now;
        setIndex((i) => (i + 1 < frames.length ? i + 1 : i));
      } else {
        forceRender((n) => n + 1);
      }
      rafId.current = requestAnimationFrame(tick);
    };
    rafId.current = requestAnimationFrame(tick);
    return () => {
      if (rafId.current !== undefined) cancelAnimationFrame(rafId.current);
    };
    // Re-arm whenever play state, the frame set, or the current index changes
    // so the timer restarts cleanly after a manual seek.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isPlaying, frames, index]);

  const currentFrame = frames[index] ?? null;
  const nextFrame = frames[index + 1] ?? null;

  const t =
    reducedMotion || !currentFrame || !nextFrame
      ? 0
      : Math.min(1, (performance.now() - stepStartedAt.current) / STEP_DURATION_MS);

  const players =
    currentFrame && nextFrame ? interpolatePlayers(currentFrame, nextFrame, t) : currentFrame?.players ?? [];
  const ball = currentFrame && nextFrame ? interpolateBall(currentFrame, nextFrame, t) : currentFrame?.ball ?? null;

  return {
    currentFrame,
    players,
    ball,
    index,
    isPlaying,
    play: () => setIsPlaying(true),
    pause: () => setIsPlaying(false),
    seek: (i: number) => setIndex(Math.max(0, Math.min(frames.length - 1, i))),
  };
}
