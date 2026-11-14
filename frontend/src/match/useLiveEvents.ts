import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { MatchEvent } from "../api/types";

const POLL_INTERVAL_MS = 1500;

export function useLiveEvents(matchId: string | null, enabled: boolean): MatchEvent[] {
  const [events, setEvents] = useState<MatchEvent[]>([]);

  useEffect(() => {
    setEvents([]);
  }, [matchId]);

  useEffect(() => {
    if (!matchId || !enabled) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const result = await api.getEvents(matchId);
        if (!cancelled) setEvents(result);
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

  return events;
}
