from blm.cache import JsonCache


def test_roundtrip(tmp_path):
    c = JsonCache(tmp_path / "c")
    assert c.get("wayback", "https://x.de/a") is None
    c.set("wayback", "https://x.de/a", {"text": "hallo", "n": 1})
    assert c.get("wayback", "https://x.de/a") == {"text": "hallo", "n": 1}


def test_namespaces_and_keys_are_independent(tmp_path):
    c = JsonCache(tmp_path)
    c.set("emb", "openai|text-embedding-3-small|hallo", {"v": [1.0]})
    assert c.get("emb", "openai|text-embedding-3-large|hallo") is None
    assert c.get("wayback", "openai|text-embedding-3-small|hallo") is None


def test_clear_removes_everything(tmp_path):
    c = JsonCache(tmp_path)
    c.set("a", "1", {"x": 1})
    c.set("b", "2", {"x": 2})
    assert c.clear() == 2
    assert c.get("a", "1") is None


def test_corrupt_file_is_treated_as_miss(tmp_path):
    c = JsonCache(tmp_path)
    c.set("a", "1", {"x": 1})
    path = next((tmp_path / "a").iterdir())
    path.write_text("{not json")
    assert c.get("a", "1") is None
