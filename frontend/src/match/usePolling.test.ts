import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { usePolling } from "./usePolling";

describe("usePolling", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("polls until stopWhen is true, then stops", async () => {
    let n = 0;
    const load = vi.fn(async () => ++n);
    const { result } = renderHook(() => usePolling("m1", load, 1000, (v: number) => v >= 3));
    await act(async () => {});
    expect(result.current).toBe(1);
    for (let i = 0; i < 5; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
    }
    expect(result.current).toBe(3);
    expect(load).toHaveBeenCalledTimes(3);
  });

  it("returns null without a key and never calls load", async () => {
    const load = vi.fn(async () => 1);
    const { result } = renderHook(() => usePolling(null, load, 1000));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(result.current).toBeNull();
    expect(load).not.toHaveBeenCalled();
  });

  it("keeps the last value through a failed poll", async () => {
    const load = vi
      .fn<(key: string) => Promise<string>>()
      .mockResolvedValueOnce("ok")
      .mockRejectedValueOnce(new Error("network"));
    const { result } = renderHook(() => usePolling("m1", load, 1000));
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current).toBe("ok");
  });
});
