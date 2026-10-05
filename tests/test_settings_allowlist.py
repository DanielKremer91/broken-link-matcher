"""The committed allowlist must stay narrow: only monitor scripts that take no free paths or recipients."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
ALLOW = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))["permissions"]["allow"]
SAFE_SCRIPTS = {"monitor_match.py", "send_report.py", "check_setup.py", "ahrefs_params.py", "backlinks_check.py",
                "frog_state.py", "frog_probe.py", "frog_crawl_check.py", "oshelp.py"}


def test_bash_rules_name_only_safe_monitor_scripts():
    for rule in ALLOW:
        if not rule.startswith("Bash("):
            continue
        if rule == "Bash(sleep *)":
            continue
        m = re.fullmatch(r"Bash\(\.venv/(bin/python|Scripts/python\.exe) ([a-z_]+\.py)( \*)?\)", rule)
        assert m, f"unexpected Bash rule: {rule}"
        assert m.group(2) in SAFE_SCRIPTS, rule
        assert (ROOT / m.group(2)).is_file(), rule


def test_no_blanket_rules():
    joined = " ".join(ALLOW)
    for forbidden in ("python *)", "python.exe *)", "cli.py", "place_frog_config.py", " -c", "Bash(*)", "Edit(**)", "mcp__"):
        assert forbidden not in joined, forbidden


def test_writing_is_limited_to_the_run_folder():
    assert [r for r in ALLOW if not r.startswith("Bash(")] == ["Edit(/laeufe/**)"]


def test_allowlisted_scripts_take_no_free_recipients_or_output_paths():
    import monitor_match
    import send_report
    import pytest
    for module, flags in ((send_report, ["--to", "--attach", "--subject"]), (monitor_match, ["--out", "--report", "--sender"])):
        for flag in flags:
            with pytest.raises(SystemExit):
                module.main(["--competitor", "x", flag, "y"])
