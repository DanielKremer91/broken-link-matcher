import numpy as np

from blm.matcher import build_results, normalize_rows, top_k
from blm.models import BrokenBacklink, OwnPage, RecoveredContent


def own():
    return [
        OwnPage("https://me.de/stahl", np.array([2.0, 0.0, 0.0], dtype=np.float32)),
        OwnPage("https://me.de/holz", np.array([0.0, 3.0, 0.0], dtype=np.float32)),
        OwnPage("https://me.de/glas", np.array([0.0, 0.0, 1.0], dtype=np.float32)),
        OwnPage("https://me.de/mix", np.array([1.0, 1.0, 0.0], dtype=np.float32)),
    ]


def bl(i, rank):
    return BrokenBacklink(url_from=f"https://s{i}.de", url_to=f"https://c.de/{i}", value_rank=rank)


def test_normalize_rows_unit_length_and_zero_safe():
    m = normalize_rows(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert np.allclose(np.linalg.norm(m[0]), 1.0)
    assert m[1].tolist() == [0.0, 0.0]


def test_top_k_orders_by_cosine():
    pages = own()
    matrix = normalize_rows(np.stack([p.vector for p in pages]))
    hits = top_k(np.array([1.0, 0.1, 0.0]), matrix, [p.url for p in pages], k=3)
    assert [h.url for h in hits] == ["https://me.de/stahl", "https://me.de/mix", "https://me.de/holz"]
    assert hits[0].score > hits[1].score > hits[2].score
    assert 0.99 < hits[0].score <= 1.0


def test_top_k_respects_fewer_pages_than_k():
    matrix = normalize_rows(np.array([[1.0, 0.0]]))
    assert len(top_k(np.array([1.0, 0.0]), matrix, ["u"], k=3)) == 1


def test_build_results_flags_gap_and_orders_priority():
    ranked = [bl(1, 1), bl(2, 2), bl(3, 3), bl(4, 4)]
    recovered = [
        RecoveredContent("https://c.de/1", "t", "wayback"),
        RecoveredContent("https://c.de/2", "t", "wayback"),
        RecoveredContent("https://c.de/3", None, "none"),
        RecoveredContent("https://c.de/4", "t", "fallback"),
    ]
    vectors = [
        np.array([0.0, 0.0, 1.0]),   # matches glas perfectly
        np.array([1.0, 1.0, 1.0]),   # best cosine ~0.816 with mix -> above 0.5, no gap
        None,
        np.array([0.0, 1.0, 0.0]),   # fallback, matches holz
    ]
    out = build_results(ranked, recovered, vectors, own(), threshold=0.9)
    # row2 best score 0.816 < 0.9 -> gap; row3 unmatched; row4 fallback matched (holz 1.0)
    assert [r.backlink.url_to for r in out] == ["https://c.de/1", "https://c.de/4", "https://c.de/2", "https://c.de/3"]
    assert [r.priority for r in out] == [1, 2, 3, 4]
    assert out[0].top[0].url == "https://me.de/glas"
    assert out[2].is_content_gap is True
    assert out[3].top == [] and out[3].is_content_gap is False
    assert any("kein Text" in e for e in out[3].errors)


def test_build_results_can_exclude_fallback_rows():
    ranked = [bl(1, 1)]
    recovered = [RecoveredContent("https://c.de/1", "t", "fallback")]
    out = build_results(ranked, recovered, [np.array([1.0, 0.0, 0.0])], own(), match_fallback=False)
    assert out[0].top == []
    assert any("Fallback" in e for e in out[0].errors)


def test_build_results_handles_failed_embedding():
    ranked = [bl(1, 1)]
    recovered = [RecoveredContent("https://c.de/1", "t", "wayback")]
    out = build_results(ranked, recovered, [None], own())
    assert out[0].top == []
    assert any("Embedding" in e for e in out[0].errors)


def test_build_results_length_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        build_results([bl(1, 1)], [], [], own())
