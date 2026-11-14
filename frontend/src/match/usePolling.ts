import { useEffect, useState } from "react";

/** Polls `load` every `intervalMs` while `key` is set. Keeps the last good
 * value through transient errors; resets when `key` changes. Read-only. */
export function usePolling<T>(
  key: string | null,
  load: (key: string) => Promise<T>,
  intervalMs: number,
  stopWhen?: (value: T) => boolean,
): T | null {
  const [state, setState] = useState<{ key: string | null; value: T | null }>({
    key: null,
    value: null,
  });

  useEffect(() => {
    if (!key) return;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | undefined;

    const poll = async () => {
      try {
        const value = await load(key);
        if (cancelled) return;
        setState({ key, value });
        if (stopWhen?.(value) && timer) clearInterval(timer);
      } catch {
        // Transient network/API errors skip this tick; the next poll retries.
      }
    };

    poll();
    timer = setInterval(poll, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
    // `load`/`stopWhen` are stable module-level functions at call sites.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, intervalMs]);

  return state.key === key ? state.value : null;
}
