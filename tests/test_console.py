import io

from blm.console import use_utf8


def test_stream_with_legacy_encoding_can_print_check_marks():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    use_utf8(stream)
    print("✓ vorhanden ○ fehlt ✗", file=stream)
    stream.flush()
    assert "✓" in raw.getvalue().decode("utf-8")


def test_streams_without_reconfigure_are_left_alone():
    use_utf8(io.StringIO())
    use_utf8(None)
