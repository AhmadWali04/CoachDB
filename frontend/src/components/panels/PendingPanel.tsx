import "./panels.css";

export function PendingPanel({ title, reason }: { title: string; reason: string }) {
  return (
    <section className="panel panel--pending" aria-label={title}>
      <h3 className="panel__title">{title}</h3>
      <p className="panel__empty">{reason}</p>
    </section>
  );
}
