from app.data.metrica import parse_metrica_events

HEADER = (
    "Team,Type,Subtype,Period,Start Frame,Start Time [s],End Frame,End Time [s],"
    "From,To,Start X,Start Y,End X,End Y"
)


def csv_of(rows: list[str]) -> str:
    return "\n".join([HEADER, *rows])


def test_returns_none_when_team_has_no_rows():
    csv_text = csv_of(["Away,PASS,,1,1,0.04,3,0.12,Player19,Player21,0.45,0.39,0.55,0.43"])
    assert parse_metrica_events(csv_text, "Home", "Sample_Game_1") is None


def test_pass_completion_counts_rows_with_a_recipient():
    csv_text = csv_of(
        [
            "Home,PASS,,1,1,0,3,0,P1,P2,0.1,0.1,0.2,0.1",  # complete
            "Home,PASS,,1,3,0,5,0,P2,,0.2,0.1,0.9,0.1",  # incomplete: no recipient
            "Away,PASS,,1,5,0,7,0,P9,P10,0.5,0.5,0.6,0.5",
        ]
    )
    profile = parse_metrica_events(csv_text, "Home", "Sample_Game_1")
    assert profile is not None
    assert profile.features["pass_completion_rate"] == 0.5


def test_long_pass_ratio_from_normalized_coordinates():
    csv_text = csv_of(
        [
            # ~0.8 of pitch length (105m) == a long pass
            "Home,PASS,,1,1,0,3,0,P1,P2,0.1,0.5,0.9,0.5",
            "Home,PASS,,1,3,0,5,0,P2,P3,0.1,0.5,0.15,0.5",  # short pass
        ]
    )
    profile = parse_metrica_events(csv_text, "Home", "Sample_Game_1")
    assert profile is not None
    assert profile.features["long_pass_ratio"] == 0.5


def test_shots_are_counted_per_team():
    csv_text = csv_of(
        [
            "Home,SHOT,,1,1,0,3,0,P1,,0.9,0.5,1.0,0.5",
            "Away,SHOT,,1,5,0,7,0,P9,,0.1,0.5,0.0,0.5",
        ]
    )
    profile = parse_metrica_events(csv_text, "Home", "Sample_Game_1")
    assert profile is not None
    assert profile.features["shots_per_match"] == 1.0


def test_pressures_are_not_fabricated_for_an_event_type_metrica_does_not_track():
    csv_text = csv_of(["Home,PASS,,1,1,0,3,0,P1,P2,0.1,0.1,0.2,0.1"])
    profile = parse_metrica_events(csv_text, "Home", "Sample_Game_1")
    assert profile is not None
    assert profile.features["pressures_per_match"] == 0.0


def test_formation_is_not_guessed_from_events_alone():
    csv_text = csv_of(["Home,PASS,,1,1,0,3,0,P1,P2,0.1,0.1,0.2,0.1"])
    profile = parse_metrica_events(csv_text, "Home", "Sample_Game_1")
    assert profile is not None
    assert profile.formation is None
