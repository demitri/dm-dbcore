"""The README's usage example has to actually run.

Documentation drifts silently: nothing fails when a code block stops working,
because nothing executes it. ``examples/quickstart.py`` is executed here, as a
subprocess, exactly as a reader would run it. It uses SQLite in a temporary
directory, so this needs no server and no configuration.

The example already found one thing this way -- SQLite reflects a bare
`pk INTEGER PRIMARY KEY` as nullable, which SQLAlchemy refuses to use as an
insert sentinel. A prose example would have shipped that.
"""

import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent
QUICKSTART = REPO / "examples" / "quickstart.py"


def test_quickstart_example_exists():
    assert QUICKSTART.is_file(), f"the README points at {QUICKSTART}, which is missing"


def test_quickstart_example_runs_clean():
    proc = subprocess.run(
        [sys.executable, str(QUICKSTART)],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    assert proc.returncode == 0, (
        f"examples/quickstart.py exited {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    assert proc.stdout.rstrip().endswith("OK"), proc.stdout


@pytest.mark.parametrize(
    "expected",
    [
        "database_type='sqlite'",
        "DatabaseConnection() is db -> True",
        "tables=['person']",
        "Person columns=['pk', 'name', 'email']",
        "['Ada Lovelace', 'Alan Turing']",
    ],
)
def test_quickstart_output_shows_what_it_claims(expected):
    """Each printed step must reflect a real result, not a hardcoded string."""
    proc = subprocess.run(
        [sys.executable, str(QUICKSTART)], capture_output=True, text=True, cwd=str(REPO)
    )
    assert expected in proc.stdout, f"missing {expected!r} in:\n{proc.stdout}"
