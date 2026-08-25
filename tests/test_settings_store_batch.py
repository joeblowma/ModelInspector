from back import settings_store


def test_set_values_coalesces_one_atomic_write_and_set_value_stays_immediate(
    monkeypatch, tmp_path
):
    path = tmp_path / "settings.jsonc"
    replacements = []
    original_replace = settings_store.os.replace

    def count_replace(source, destination):
        replacements.append((source, destination))
        original_replace(source, destination)

    monkeypatch.setattr(settings_store.os, "replace", count_replace)
    store = settings_store.open_settings(path, defer_initial_save=True)
    store.setValues({"analysis_threads": "4", "default_tab": "data"})
    assert len(replacements) == 1
    assert settings_store.open_settings(path).value("default_tab") == "data"

    replacements.clear()
    store.setValue("add_mode", "additive")
    assert len(replacements) == 1
