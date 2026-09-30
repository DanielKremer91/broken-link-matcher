from pathlib import Path

import httpx
import respx

from blm.models import BrokenBacklink, MatchResult, RecoveredContent
from blm.verify import canonical, verify_backlink, verify_results

FIX = Path(__file__).parent / "fixtures"
WITH = (FIX / "referring_with_link.html").read_text()
WITHOUT = (FIX / "referring_without_link.html").read_text()
FROM = "https://blog.example/kueche"
DEAD = "https://konkurrent.de/ratgeber/stahl"


def bl():
    return BrokenBacklink(url_from=FROM, url_to=DEAD)


def test_canonical():
    assert canonical("HTTPS://Konkurrent.de/ratgeber/stahl/#x") == "konkurrent.de/ratgeber/stahl"
    assert canonical("http://konkurrent.de/ratgeber/stahl") == canonical(DEAD)


@respx.mock
def test_confirmed_when_404_and_link_present():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(return_value=httpx.Response(200, text=WITH))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "confirmed"


@respx.mock
def test_fixed_when_target_alive():
    respx.get(DEAD).mock(return_value=httpx.Response(200, text="ok"))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "fixed"


@respx.mock
def test_fixed_when_link_removed():
    respx.get(DEAD).mock(return_value=httpx.Response(410))
    respx.get(FROM).mock(return_value=httpx.Response(200, text=WITHOUT))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "fixed"


@respx.mock
def test_unknown_on_timeout():
    respx.get(DEAD).mock(side_effect=httpx.ConnectTimeout("slow"))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "unknown"


@respx.mock
def test_verify_results_sets_field_and_pauses_between_domains():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(return_value=httpx.Response(200, text=WITH))
    respx.get("https://other.example/p").mock(return_value=httpx.Response(200, text=WITH))
    rows = [
        MatchResult(bl(), RecoveredContent(DEAD, "t", "wayback")),
        MatchResult(BrokenBacklink(url_from="https://other.example/p", url_to=DEAD), RecoveredContent(DEAD, "t", "wayback")),
    ]
    pauses = []
    seen = []
    with httpx.Client() as c:
        verify_results(rows, c, sleeper=pauses.append, progress=lambda i, n: seen.append((i, n)))
    assert [r.verification for r in rows] == ["confirmed", "confirmed"]
    assert pauses == [0.5]
    assert seen == [(1, 2), (2, 2)]
