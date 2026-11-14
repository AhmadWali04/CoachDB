// Recorded simulator output from `frontend/src/fixtures/` (CHECKLIST.md rule
// 7). Never hand-invent frames here -- this only discovers and loads files
// that Track A exports from a real seeded run.
import type { FramesPage } from "../api/types";

const fixtureModules = import.meta.glob<FramesPage>("../fixtures/*.json", {
  import: "default",
});

export function listFixtureNames(): string[] {
  return Object.keys(fixtureModules)
    .map((path) => path.split("/").pop() ?? path)
    .map((file) => file.replace(/\.json$/, ""))
    .sort();
}

export async function loadFixture(name: string): Promise<FramesPage | null> {
  const key = Object.keys(fixtureModules).find((path) => path.endsWith(`/${name}.json`));
  if (!key) return null;
  const load = fixtureModules[key];
  return load();
}
