"""Check the pure-Python REQreate patch applier."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apply_reqreate_patch import apply_patch


PATCH = """\
diff --git a/pkg/a.py b/pkg/a.py
--- a/pkg/a.py
+++ b/pkg/a.py
@@ -2,3 +2,3 @@
 two
-three
+THREE
 four
@@ -6,2 +6,2 @@
 six
-seven
\\ No newline at end of file
+seven
diff --git a/pkg/missing.json b/pkg/missing.json
--- a/pkg/missing.json
+++ b/pkg/missing.json
@@ -1 +1 @@
-old
+new
"""


def write_tree(directory, newline):
    root = Path(directory)
    (root / "pkg").mkdir()
    # An extra leading line shifts every hunk by one, as in the real package.
    lines = ["zero", "one", "two", "three", "four", "five", "six", "seven"]
    (root / "pkg" / "a.py").write_bytes(newline.join(lines).encode())
    patch_path = root / "fix.patch"
    patch_path.write_bytes(PATCH.replace("\n", "\r\n").encode())
    return root, patch_path


def test_apply_patch():
    for newline in ("\n", "\r\n"):
        check_apply_patch(newline)


def check_apply_patch(newline):
    with TemporaryDirectory() as directory:
        root, patch_path = write_tree(directory, newline)
        assert apply_patch(root, patch_path) == {
            "pkg/a.py": "patched",
            "pkg/missing.json": "skipped (not in this REQreate release)",
        }
        expected = newline.join(
            ["zero", "one", "two", "THREE", "four", "five", "six", "seven", ""])
        assert (root / "pkg" / "a.py").read_bytes().decode() == expected
        assert apply_patch(root, patch_path)["pkg/a.py"] == "already patched"
        assert (root / "pkg" / "a.py").read_bytes().decode() == expected


def test_apply_patch_mismatch_writes_nothing():
    with TemporaryDirectory() as directory:
        root, patch_path = write_tree(directory, "\n")
        (root / "pkg" / "a.py").write_text("unrelated\n", encoding="utf-8")
        try:
            apply_patch(root, patch_path)
        except ValueError as error:
            assert "does not match" in str(error)
        else:
            raise AssertionError("expected a mismatch error")
        assert (root / "pkg" / "a.py").read_text(encoding="utf-8") == "unrelated\n"
