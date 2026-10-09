"""Check the project's direct Python dependencies in the active environment."""

from importlib import import_module
from importlib.metadata import version
from pathlib import Path
import re


REQUIREMENTS_PATH = Path(__file__).with_name("requirements.txt")


def missing_dependencies(requirements_path=REQUIREMENTS_PATH):
    """Return requirements whose packages cannot be imported by this Python."""
    missing = []
    for line in requirements_path.read_text().splitlines():
        requirement = line.split("#", 1)[0].strip()
        if not requirement:
            continue
        distribution = re.split(r"[<>=!~;\[]", requirement, 1)[0]
        package = "REQreate" if distribution == "reqreate" else distribution
        if package == "scikit-learn":
            package = "sklearn"
        try:
            import_module(package)
        except ImportError:
            missing.append(package)
        else:
            if package == "osmnx" and not version(package).startswith("2."):
                missing.append(requirement)
    return missing


if __name__ == "__main__":
    missing = missing_dependencies()
    if missing:
        raise SystemExit(
            f"Missing Python dependencies: {', '.join(missing)}\n"
            "Install with: uv pip install --python .venv/bin/python -r requirements.txt"
        )
    print("All direct Python dependencies are installed.")
