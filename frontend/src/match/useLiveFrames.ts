import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Frame } from "../api/types";

const POLL_INTERVAL_MS = 1000;

/** Polls `/matches/{id}/frames` and accumulates new frames by sequence
 * number. Used once a real match is running, in place of the fixture. */
export function useLiveFrames(matchId: string | null, enabled: boolean): Frame[] {
  const [frames, setFrames] = useState<Frame[]>([]);
  const nextSeqRef = useRef(0);

  useEffect(() => {
    setFrames([]);
    nextSeqRef.current = 0;
  }, [matchId]);

  useEffect(() => {
    if (!matchId || !enabled) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const page = await api.getFrames(matchId, nextSeqRef.current);
        if (cancelled) return;
        if (page.frames.length > 0) {
          setFrames((prev) => [...prev, ...page.frames]);
        }
        if (page.next_seq !== null && page.next_seq !== undefined) {
          nextSeqRef.current = page.next_seq;
        }
      } catch {
        // Transient network/API errors skip this tick; the next poll retries.
      }
    };

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [matchId, enabled]);

  return frames;
}
