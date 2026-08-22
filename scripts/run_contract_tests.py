from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    environment = os.environ.copy()
    source_root = str(REPOSITORY_ROOT / "src")
    existing_python_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = (
        source_root
        if not existing_python_path
        else os.pathsep.join((source_root, existing_python_path))
    )

    python_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
            "-v",
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
    )

    npm_executable = shutil.which("npm")
    if npm_executable is None:
        print("npm executable was not found", file=sys.stderr)
        return 127

    typescript_result = subprocess.run(
        [npm_executable, "test"],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    return 0 if python_result.returncode == typescript_result.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
