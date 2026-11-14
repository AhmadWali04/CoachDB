import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pymongo.errors import CollectionInvalid, OperationFailure

from app.data import experience_index as module
from app.data.experience_index import IndexDefinitionMismatch, provision_experience_index
from app.data.indexes import EXPERIENCE_INDEX, vector_index_definition

DIMENSIONS = 8
DEFINITION = vector_index_definition(DIMENSIONS, experiences=True)


def ready(**kwargs):
    return {"latestDefinition": DEFINITION, "status": "READY", "queryable": True, **kwargs}


def database(indexes, *, exists=True):
    db = MagicMock()
    db.list_collection_names.return_value = ["coach_experiences"] if exists else []
    db.__getitem__.return_value.list_search_indexes.side_effect = indexes
    return db


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(now=0.0)

    def sleep(seconds):
        state.now += seconds

    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: state.now, sleep=sleep))
    return state


def test_creates_empty_collection_and_index_then_verifies_ready():
    db = database([[], [ready()]], exists=False)
    result = provision_experience_index(db, DIMENSIONS)
    assert result.created_collection and result.created_index
    assert result.status == "READY"
    db.create_collection.assert_called_once_with("coach_experiences")
    collection = db.__getitem__.return_value
    model = collection.create_search_index.call_args.args[0]
    assert model.document == {
        "name": EXPERIENCE_INDEX,
        "type": "vectorSearch",
        "definition": DEFINITION,
    }
    assert all(
        call.args == (EXPERIENCE_INDEX,) for call in collection.list_search_indexes.call_args_list
    )
    collection.insert_one.assert_not_called()
    collection.update_search_index.assert_not_called()
    collection.drop_search_index.assert_not_called()


def test_existing_matching_index_is_idempotent():
    db = database([[ready()], [ready()]])
    result = provision_experience_index(db, DIMENSIONS)
    assert not result.created_collection and not result.created_index
    db.create_collection.assert_not_called()
    db.__getitem__.return_value.create_search_index.assert_not_called()


def test_collection_creation_race_does_not_overwrite_data():
    db = database([[], [ready()]], exists=False)
    db.create_collection.side_effect = CollectionInvalid("already exists")
    result = provision_experience_index(db, DIMENSIONS)
    assert not result.created_collection
    assert result.created_index


def test_reordered_fields_are_equivalent():
    reordered = {"fields": list(reversed(DEFINITION["fields"]))}
    db = database([[ready(latestDefinition=reordered)], [ready(latestDefinition=reordered)]])
    assert provision_experience_index(db, DIMENSIONS).status == "READY"
    db.__getitem__.return_value.create_search_index.assert_not_called()


@pytest.mark.parametrize(
    "definition", [None, vector_index_definition(9, experiences=True), vector_index_definition(8)]
)
def test_incompatible_index_is_never_rebuilt(definition):
    db = database([[ready(latestDefinition=definition)]])
    with pytest.raises(IndexDefinitionMismatch):
        provision_experience_index(db, DIMENSIONS)
    collection = db.__getitem__.return_value
    collection.create_search_index.assert_not_called()
    collection.update_search_index.assert_not_called()
    collection.drop_search_index.assert_not_called()


def test_definition_change_during_wait_fails_closed():
    db = database([[ready()], [ready(latestDefinition=vector_index_definition(9))]])
    with pytest.raises(IndexDefinitionMismatch):
        provision_experience_index(db, DIMENSIONS)


def test_waits_until_both_ready_and_queryable(clock):
    db = database(
        [
            [],
            [ready(status="PENDING", queryable=False)],
            [ready(status="READY", queryable=False)],
            [ready()],
        ]
    )
    assert provision_experience_index(db, DIMENSIONS).status == "READY"
    assert clock.now == 0.5


def test_timeout_does_not_report_submission_as_success(clock):
    db = database([[], [], [], [], []])
    with pytest.raises(TimeoutError, match="may still be building"):
        provision_experience_index(db, DIMENSIONS, timeout_s=0.5)
    assert clock.now == 0.5


@pytest.mark.parametrize("status", ["FAILED", "DELETING"])
def test_failed_or_deleted_index_stops_polling(status):
    db = database([[ready()], [ready(status=status)]])
    with pytest.raises(RuntimeError, match=status):
        provision_experience_index(db, DIMENSIONS)


@pytest.mark.parametrize(
    "options",
    [
        {"dimensions": 0},
        {"dimensions": True},
        {"timeout_s": 0},
        {"timeout_s": float("nan")},
        {"timeout_s": 301},
    ],
)
def test_invalid_settings_make_no_database_calls(options):
    db = MagicMock()
    with pytest.raises(ValueError):
        provision_experience_index(db, **({"dimensions": DIMENSIONS} | options))
    assert db.mock_calls == []


@pytest.fixture
def cli():
    path = Path(__file__).resolve().parents[4] / "scripts" / "provision_experience_index.py"
    spec = importlib.util.spec_from_file_location("provision_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_preview_needs_no_credentials_or_connection(cli, monkeypatch, capsys):
    settings = MagicMock(side_effect=AssertionError("dry-run must not read configuration"))
    monkeypatch.setattr(cli, "Settings", settings)
    assert cli.main(["--dimensions", "8"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "dry-run"
    assert result["definition"] == DEFINITION
    settings.assert_not_called()


def test_cli_apply_requires_uri(cli, monkeypatch, capsys):
    monkeypatch.setattr(cli, "Settings", lambda **kwargs: SimpleNamespace(mongodb_uri=None))
    assert cli.main(["--dimensions", "8", "--apply"]) == 1
    assert "MONGODB_URI is required" in capsys.readouterr().err


def test_cli_sanitizes_database_errors(cli, monkeypatch, capsys):
    from pydantic import SecretStr

    monkeypatch.setattr(
        cli,
        "Settings",
        lambda **kwargs: SimpleNamespace(
            mongodb_uri=SecretStr("mongodb://private-user:private-password@example.test"),
            mongodb_database="test",
        ),
    )
    client = MagicMock()
    monkeypatch.setattr("pymongo.MongoClient", lambda *args, **kwargs: client)
    monkeypatch.setattr(
        cli,
        "provision_experience_index",
        MagicMock(side_effect=OperationFailure("private-password private-host")),
    )
    assert cli.main(["--dimensions", "8", "--apply"]) == 1
    output = capsys.readouterr()
    assert "MongoDB index setup failed" in output.err
    assert "private" not in output.err + output.out
    client.__exit__.assert_called_once()


def test_cli_apply_reports_verified_result(cli, monkeypatch, capsys):
    from pydantic import SecretStr

    monkeypatch.setattr(
        cli,
        "Settings",
        lambda **kwargs: SimpleNamespace(
            mongodb_uri=SecretStr("mongodb://example.test"),
            mongodb_database="test",
        ),
    )
    client = MagicMock()
    monkeypatch.setattr("pymongo.MongoClient", lambda *args, **kwargs: client)
    provision = MagicMock(return_value=module.ProvisionResult(False, False, "READY"))
    monkeypatch.setattr(cli, "provision_experience_index", provision)
    assert cli.main(["--dimensions", "8", "--apply", "--wait-seconds", "4"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "READY"
    assert provision.call_args.kwargs == {"timeout_s": 4.0}
