import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent


def _index_modes() -> dict[str, str]:
    """Map of tracked path -> git index mode (e.g. '100755')."""
    out = subprocess.run(
        ["git", "ls-files", "-s"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO,
    ).stdout
    modes = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        modes[path] = meta.split(" ", 1)[0]
    return modes


def _has_shebang(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(2) == b"#!"
    except OSError:
        return False


def test_shebang_scripts_are_executable_in_git_index():
    """A fresh clone or plugin install must receive executable scripts.

    The working tree can lie when core.fileMode=false (as in this repo), so
    check the git index mode — that is what clones and plugin installs get.
    A 100644 here means `airtable-export-schema` fails with exit 126
    "Permission denied" on every other machine. Mirrors the hk
    `exec-bit-scripts` pre-commit step: any tracked file whose first line is
    a shebang must be mode 100755. Fix: git update-index --chmod=+x <file>
    """
    modes = _index_modes()
    bad = [
        path
        for path, mode in modes.items()
        if mode == "100644" and _has_shebang(REPO / path)
    ]
    assert not bad, (
        "shebang scripts missing the executable bit in the git index "
        "(fix: git update-index --chmod=+x <file>):\n" + "\n".join(bad)
    )
    # Sanity-check the detection: the shipped bin scripts must be among the
    # executables, otherwise the shebang scan is silently matching nothing.
    assert modes.get("bin/airtable-export-schema") == "100755"
