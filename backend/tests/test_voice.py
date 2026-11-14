from datetime import UTC, datetime

import pytest

from app.schemas import AudioStatus, CoachDecision, TeamId
from app.voice import (
    AudioCache,
    BriefingNotFoundError,
    BriefingService,
    FakeTextToSpeechClient,
    InMemoryCoachDecisionReader,
)

from .test_schemas import plan_payload

NOW = datetime.now(UTC)


def decision_payload(**overrides):
    payload = {
        "decision_id": "decision_001",
        "match_id": "match_001",
        "team_id": "blue",
        "coach_id": "coach_blue",
        "analysis": {
            "match_id": "match_001",
            "team_id": "blue",
            "state_version": 12,
            "summary": "Dominant down the left in the first half.",
        },
        "scouting": {
            "match_id": "match_001",
            "team_id": "blue",
            "rival_team_id": "red",
            "state_version": 12,
            "observed_tactics": {},
        },
        "plan": plan_payload(),
        "created_at": NOW.isoformat(),
    }
    payload.update(overrides)
    return payload


def make_service(tmp_path, *, tts=None, voice_ids=None, decision=None):
    decisions = InMemoryCoachDecisionReader()
    if decision is not None:
        decisions.put(decision)
    cache = AudioCache(tmp_path / "audio")
    service = BriefingService(
        decisions=decisions,
        cache=cache,
        tts=tts,
        voice_ids=voice_ids or {TeamId.BLUE: "voice_blue", TeamId.RED: "voice_red"},
    )
    return service, decisions


def test_missing_decision_raises_not_found(tmp_path):
    service, _ = make_service(tmp_path)
    with pytest.raises(BriefingNotFoundError):
        service.get_briefing("match_001", TeamId.BLUE)


def test_briefing_transcript_is_the_approved_voice_script(tmp_path):
    decision = CoachDecision.model_validate(decision_payload())
    service, _ = make_service(tmp_path, decision=decision)
    briefing = service.get_briefing("match_001", TeamId.BLUE)
    assert briefing.transcript == decision.plan.voice_script
    assert briefing.briefing_id == decision.decision_id
    assert briefing.team_id == TeamId.BLUE


def test_audio_generated_once_and_served_from_cache_on_repeat_calls(tmp_path):
    decision = CoachDecision.model_validate(decision_payload())
    tts = FakeTextToSpeechClient()
    service, _ = make_service(tmp_path, tts=tts, decision=decision)

    first = service.get_briefing("match_001", TeamId.BLUE)
    second = service.get_briefing("match_001", TeamId.BLUE)

    assert first.audio_status == AudioStatus.READY
    assert first.audio_url == second.audio_url
    assert len(tts.calls) == 1, "audio must be cached, not regenerated per call"


def test_tts_failure_falls_back_to_text_without_raising(tmp_path):
    decision = CoachDecision.model_validate(decision_payload())
    tts = FakeTextToSpeechClient(fail=True)
    service, _ = make_service(tmp_path, tts=tts, decision=decision)

    briefing = service.get_briefing("match_001", TeamId.BLUE)

    assert briefing.audio_status == AudioStatus.UNAVAILABLE
    assert briefing.audio_url is None
    assert briefing.transcript == decision.plan.voice_script


def test_missing_voice_id_skips_tts_entirely(tmp_path):
    decision = CoachDecision.model_validate(decision_payload())
    tts = FakeTextToSpeechClient()
    service, _ = make_service(
        tmp_path, tts=tts, voice_ids={TeamId.BLUE: None, TeamId.RED: "voice_red"}, decision=decision
    )

    briefing = service.get_briefing("match_001", TeamId.BLUE)

    assert briefing.audio_status == AudioStatus.UNAVAILABLE
    assert tts.calls == []


def test_no_tts_client_configured_is_unavailable_not_an_error(tmp_path):
    decision = CoachDecision.model_validate(decision_payload())
    service, _ = make_service(tmp_path, tts=None, decision=decision)

    briefing = service.get_briefing("match_001", TeamId.BLUE)

    assert briefing.audio_status == AudioStatus.UNAVAILABLE
    assert briefing.audio_url is None
