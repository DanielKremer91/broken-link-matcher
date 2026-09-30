from pathlib import Path

import numpy as np
from streamlit.testing.v1 import AppTest

from blm.ingest.frog_csv import FrogImport
from blm.models import BrokenBacklink, OwnPage, RecoveredContent

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_app_renders_sidebar_and_first_sections():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    headers = [h.value for h in at.header]
    assert any(h.startswith("1.") for h in headers)
    assert any(h.startswith("2.") for h in headers)
    assert at.sidebar.selectbox[0].value == "openai"


def test_app_renders_all_five_sections_with_seeded_state():
    at = AppTest.from_file(APP, default_timeout=30)
    pages = [OwnPage("https://me.de/a", np.array([1.0, 0.0], dtype=np.float32), title="Seite A"),
             OwnPage("https://me.de/b", np.array([0.0, 1.0], dtype=np.float32))]
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://c.de/x", anchor="x", domain_rating=50.0)
    at.session_state["frog"] = FrogImport(pages=pages, dimension=2, skipped=0)
    at.session_state["frog_name"] = "frog.csv"
    at.session_state["dim_ok"] = True
    at.session_state["probe_dim"] = 2
    at.session_state["raw_backlinks"] = [bl]
    at.session_state["recovered_for"] = [BrokenBacklink(**{**bl.__dict__, "value_rank": 1})]
    at.session_state["recovered"] = [RecoveredContent("https://c.de/x", "text", "wayback", "20240101000000")]
    at.session_state["vectors"] = [np.array([1.0, 0.0], dtype=np.float32)]
    at.run()
    assert not at.exception
    numbers = sorted(h.value[0] for h in at.header if h.value[0].isdigit())
    assert numbers == ["1", "2", "3", "4", "5"]
    assert len(at.session_state["results"]) == 1
    assert at.session_state["results"][0].top[0].url == "https://me.de/a"
