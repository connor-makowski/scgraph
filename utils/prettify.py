import subprocess
import sys
from pathlib import Path

root = Path(__file__).parent.parent

subprocess.run(
    [
        sys.executable, "-m", "ruff", "check",
        "--select", "F401",
        "--fix",
        "--quiet",
        str(root / "scgraph"),
    ],
    check=True,
)
subprocess.run(
    [sys.executable, "-m", "black", "--config", str(root / "pyproject.toml"), str(root / "scgraph")],
    check=True,
)
subprocess.run(
    [sys.executable, "-m", "black", "--config", str(root / "pyproject.toml"), str(root / "test")],
    check=True,
)
