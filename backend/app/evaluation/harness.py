"""Independent metrics from persisted evidence and side-swapped seeded trials."""

from app.schemas import TeamId


def evaluate(documents, events_by_match):
    metrics = {}
    for team in TeamId:
        rows = []
        for doc in documents:
            engine = doc["_engine"]
            decision = engine["decisions"][team.value]
            rival = TeamId.RED if team == TeamId.BLUE else TeamId.BLUE
            rival_plan = engine["decisions"][rival.value]["plan"]["plan"]
            actions = [a for a in engine["actions"].values() if a["team_id"] == team]
            events = events_by_match[doc["match_id"]]
            observations = (
                decision["analysis"]["own_strengths"] + decision["analysis"]["own_weaknesses"]
            )
            refs = [r for o in observations for r in o["evidence"]] + decision["plan"][
                "opponent_prediction"
            ]["evidence"]
            known = {e.event_id for e in events} | {
                "metric:shots",
                "metric:turnovers",
                "metric:score",
                "metric:possession_pct",
                "metric:pressing_successes",
            }
            shots = [
                sum(e.type == "shot" and e.team_id == team and e.half == half for e in events)
                for half in (1, 2)
            ]
            rows.append(
                {
                    "prediction_accuracy": float(
                        decision["plan"]["opponent_prediction"]["likely_change"]
                        == rival_plan["mentality"]
                    ),
                    "decision_validity": float(not decision["used_fallback"]),
                    "execution_reliability": sum(a["status"] == "verified" for a in actions)
                    / max(len(actions), 1),
                    "recovery_correctness": float(
                        not engine["crash_fired"]
                        or (
                            engine["recoveries"] > 0
                            and len(engine["runtime"]["applied_actions"]) == 2
                            and all(a["status"] == "verified" for a in actions)
                        )
                    ),
                    "evidence_grounding": sum(r in known for r in refs) / max(len(refs), 1),
                    "avg_decision_latency_ms": engine.get("decision_latency_ms", {}).get(
                        team.value, 0.0
                    ),
                    "shot_delta": shots[1] - shots[0],
                    "goal_difference": doc["score"][team.value] - doc["score"][rival.value],
                }
            )
        metrics[team.value] = (
            {key: sum(row[key] for row in rows) / len(rows) for key in rows[0]} if rows else {}
        )
    return metrics
