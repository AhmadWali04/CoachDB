// Historical data informs coach memory/benchmarks only; the simulator
// remains the source of truth for the simulated match (PRD §14.2).
export const DATASET_ATTRIBUTIONS = [
  {
    name: "StatsBomb Open Data",
    url: "https://github.com/statsbomb/open-data",
    note: "event-level data, used for analyst/scout style profiles",
  },
  {
    name: "Metrica Sports Sample Data",
    url: "https://github.com/metrica-sports/sample-data",
    note: "anonymized tracking + event data; teams/players are not identified",
  },
];
