import json

import train


def test_pick_device_respects_an_explicit_choice():
    assert train.pick_device("cpu") == "cpu"


def test_update_state_merges_fields_into_runs_state_json(tmp_path, monkeypatch):
    monkeypatch.setattr(train, "STATE", tmp_path / "runs" / "state.json")
    train.update_state(state="running", epochs=40)
    train.update_state(epoch=3)
    state = json.loads((tmp_path / "runs" / "state.json").read_text())
    assert state["state"] == "running" and state["epochs"] == 40 and state["epoch"] == 3
