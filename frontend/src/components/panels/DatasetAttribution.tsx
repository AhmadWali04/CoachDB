import { DATASET_ATTRIBUTIONS } from "../../data/attribution";
import "./panels.css";

export function DatasetAttribution() {
  return (
    <footer className="panel" aria-label="Dataset attribution">
      <h3 className="panel__title">Data sources</h3>
      <ul className="panel__empty" style={{ listStyle: "none", padding: 0, margin: 0 }}>
        {DATASET_ATTRIBUTIONS.map((dataset) => (
          <li key={dataset.name}>
            <a href={dataset.url} target="_blank" rel="noreferrer">
              {dataset.name}
            </a>{" "}
            — {dataset.note}
          </li>
        ))}
      </ul>
    </footer>
  );
}
