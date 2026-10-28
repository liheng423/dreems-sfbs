"""Apply src/reqreate/instance_generator.patch to the installed REQreate package.

Pure Python, so it behaves the same on every OS and shell and needs no
external `patch` tool. Safe to run again: hunks already applied are skipped.
"""

from pathlib import Path


PATCH_PATH = Path(__file__).parent / "src" / "reqreate" / "instance_generator.patch"
REINSTALL_HINT = "Reinstall a clean copy with: uv pip install --reinstall reqreate==0.1.1"


def parse_patch(text):
    """Return {target: [hunk, ...]} for a unified diff with a/ b/ prefixes.

    Each hunk is a dict with the 0-based `start` line, the `old` and `new`
    lines, and `old_eol`/`new_eol`, which say whether that side ends with a
    newline when the hunk reaches the end of the file.
    """
    files = {}
    hunk = None
    last = None
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("diff "):
            hunk = None
        elif line.startswith("+++ b/"):
            hunks = files.setdefault(line[len("+++ b/"):], [])
        elif line.startswith("@@ "):
            start = int(line.split()[1].split(",")[0][1:])
            hunk = {"start": max(start - 1, 0), "old": [], "new": [],
                    "old_eol": True, "new_eol": True}
            hunks.append(hunk)
        elif hunk is None:
            continue
        elif line.startswith("\\"):
            if last in " -":
                hunk["old_eol"] = False
            if last in " +":
                hunk["new_eol"] = False
        elif line[:1] in (" ", "-", "+"):
            last = line[0]
            if last in " -":
                hunk["old"].append(line[1:])
            if last in " +":
                hunk["new"].append(line[1:])
    return files


def find_block(lines, block, guess):
    """Return the index of block in lines closest to guess, or None."""
    positions = range(len(lines) - len(block) + 1)
    for i in sorted(positions, key=lambda i: abs(i - guess)):
        if lines[i:i + len(block)] == block:
            return i
    return None


def apply_hunks(text, hunks, target="file"):
    """Return text with hunks applied; hunks already applied are left as is."""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    eol = lines[-1] == ""
    if eol:
        lines.pop()
    offset = 0
    for hunk in hunks:
        old, new = hunk["old"], hunk["new"]
        at = find_block(lines, old, hunk["start"] + offset)
        if at is None:
            if find_block(lines, new, hunk["start"] + offset) is None:
                raise ValueError(
                    f"{target}: hunk at line {hunk['start'] + 1} does not match "
                    f"the installed file.\n{REINSTALL_HINT}"
                )
            continue
        if at + len(old) == len(lines):
            eol = hunk["new_eol"]
        lines[at:at + len(old)] = new
        offset += len(new) - len(old)
    return newline.join(lines) + (newline if eol else "")


def apply_patch(root, patch_path=PATCH_PATH):
    """Patch the REQreate files under root and return {target: status}.

    Nothing is written unless every file can be patched. Files missing from
    the installed package are skipped: the PyPI release of REQreate does not
    ship schema/config.schema.json.
    """
    status = {}
    updates = {}
    for target, hunks in parse_patch(patch_path.read_text(encoding="utf-8")).items():
        path = root / target
        if not path.exists():
            status[target] = "skipped (not in this REQreate release)"
            continue
        text = path.read_bytes().decode("utf-8")
        patched = apply_hunks(text, hunks, target)
        if patched == text:
            status[target] = "already patched"
        else:
            status[target] = "patched"
            updates[path] = patched
    for path, patched in updates.items():
        path.write_bytes(patched.encode("utf-8"))
    return status


if __name__ == "__main__":
    import REQreate

    root = Path(REQreate.__file__).parents[1]
    try:
        status = apply_patch(root)
    except ValueError as error:
        raise SystemExit(f"REQreate was not changed. {error}")
    for target, result in status.items():
        print(f"{target}: {result}")
    print("Run python check_dependencies.py to confirm.")
