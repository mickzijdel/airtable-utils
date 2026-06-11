import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent


def test_scripts_are_executable_in_git_index():
    """A fresh clone or plugin install must receive executable scripts.

    The working tree can lie when core.fileMode=false (as in this repo), so
    check the git index mode — that is what clones and plugin installs get.
    A 100644 here means `airtable-export-schema` fails with exit 126
    "Permission denied" on every other machine.
    """
    out = subprocess.run(
        ["git", "ls-files", "-s", "bin/", "scripts/"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout
    assert out, "expected git-tracked files under bin/ and scripts/"
    bad = [line for line in out.splitlines() if not line.startswith("100755")]
    assert not bad, "non-executable scripts in git index:\n" + "\n".join(bad)
