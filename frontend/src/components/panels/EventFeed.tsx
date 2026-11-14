import type { MatchEvent } from "../../api/types";
import "./panels.css";

export function EventFeed({ events }: { events: MatchEvent[] }) {
  const recent = events.slice(-20).reverse();

  return (
    <section className="panel" aria-label="Event feed">
      <h3 className="panel__title">Event feed</h3>
      {recent.length === 0 ? (
        <p className="panel__empty">No events yet.</p>
      ) : (
        <ul className="event-feed">
          {recent.map((event) => (
            <li key={event.event_id} className="event-feed__item">
              <span className="event-feed__minute">{event.clock_minute}&apos;</span>
              <span className="event-feed__type">{event.type.replace(/_/g, " ")}</span>
              {event.team_id && <span className="event-feed__team">{event.team_id}</span>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
