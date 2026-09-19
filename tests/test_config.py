import json

import config


def _point_at(tmp_path, monkeypatch, data=None):
    path = tmp_path / "config.json"
    if data is not None:
        path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", path)
    return path


def test_old_multimodal_keys_are_read_under_their_new_names(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch, {
        "use_multimodal": True,
        "multimodal_level": "advanced",
        "multimodal_timeout_seconds": 12,
        "multimodal_output_mode": "translate",
        "multimodal_providers": [{"id": "groq", "display_name": "Groq", "base_url": None}],
        "multimodal_models": [{"id": "groq::m", "provider_id": "groq", "model": "groq/m"}],
        "active_multimodal_model_id": "groq::m",
    })
    loaded = config.load_config()
    assert loaded["use_cleanup"] is True
    assert loaded["cleanup_level"] == "advanced"
    assert loaded["cleanup_timeout_seconds"] == 12
    assert loaded["cleanup_output_mode"] == "translate"
    assert loaded["cleanup_providers"][0]["id"] == "groq"
    assert loaded["active_cleanup_model_id"] == "groq::m"
    assert not any(key.startswith(("multimodal_", "use_multimodal")) for key in loaded)


def test_new_key_wins_over_a_leftover_old_one(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch, {"cleanup_level": "basic", "multimodal_level": "advanced"})
    assert config.load_config()["cleanup_level"] == "basic"


def test_saving_writes_only_new_names(tmp_path, monkeypatch):
    path = _point_at(tmp_path, monkeypatch, {"multimodal_level": "advanced"})
    config.save_config(config.load_config())
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["cleanup_level"] == "advanced"
    assert not any("multimodal" in key for key in saved)


def test_legacy_transliteration_flag_still_maps_to_output_mode(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch, {"force_english_transliteration": True})
    loaded = config.load_config()
    assert loaded["cleanup_output_mode"] == "transliterate"


def test_fresh_install_ships_ollama_on_ipv4_loopback(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    providers = config.load_config()["cleanup_providers"]
    assert [p["id"] for p in providers] == ["ollama"]
    assert providers[0]["base_url"] == "http://127.0.0.1:11434"


def test_defaults_are_not_shared_between_loads(tmp_path, monkeypatch):
    _point_at(tmp_path, monkeypatch)
    first = config.load_config()
    first["cleanup_providers"].append({"id": "x"})
    first["custom_words"].append("word")
    second = config.load_config()
    assert [p["id"] for p in second["cleanup_providers"]] == ["ollama"]
    assert second["custom_words"] == []
