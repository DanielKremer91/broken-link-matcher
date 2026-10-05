"""Console output that also works on Windows.

When output is piped, Python on Windows encodes it with a legacy code page that
has no check mark or cross. The scripts therefore switch their output to UTF-8.
"""

from __future__ import annotations

import sys


def use_utf8(*streams) -> None:
    """Switch the given streams (default: stdout and stderr) to UTF-8 where possible."""
    for stream in streams or (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
