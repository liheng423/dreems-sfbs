"""Check the project's direct Python dependencies in the active environment."""

from importlib import import_module
from importlib.metadata import version
from pathlib import Path
import re


REQUIREMENTS_PATH = Path(__file__).with_name("requirements.txt")
PATCH_PATH = Path(__file__).parent / "src" / "reqreate" / "instance_generator.patch"


def missing_dependencies(requirements_path=REQUIREMENTS_PATH):
    """Return requirements whose packages cannot be imported by this Python."""
    missing = []
    for line in requirements_path.read_text(encoding="utf-8").splitlines():
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


def unpatched_reqreate_files(patch_path=PATCH_PATH):
    """Return installed REQreate files that lack lines added by the patch.

    Files missing from the installed package are skipped: the PyPI release
    of REQreate does not ship schema/config.schema.json.
    """
    import REQreate

    root = Path(REQreate.__file__).parents[1]
    added = {}
    target = None
    for line in patch_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("+++ b/"):
            target = line[len("+++ b/"):]
            added[target] = []
        elif line.startswith("+") and target and line[1:].strip():
            added[target].append(line[1:].strip())
    unpatched = []
    for target, lines in added.items():
        path = root / target
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if not all(line in text for line in lines):
            unpatched.append(target)
    return unpatched


if __name__ == "__main__":
    missing = missing_dependencies()
    if missing:
        raise SystemExit(
            f"Missing Python dependencies: {', '.join(missing)}\n"
            "Install with: uv pip install -r requirements.txt"
        )
    print("All direct Python dependencies are installed.")
    unpatched = unpatched_reqreate_files()
    if unpatched:
        raise SystemExit(
            f"REQreate is not patched: {', '.join(unpatched)}\n"
            "Apply src/reqreate/instance_generator.patch as described in README.md."
        )
    print("REQreate is patched.")
