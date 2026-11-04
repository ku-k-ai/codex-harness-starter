"""デモの検証器が、単純連結という不正な実装を見逃さないことを確認。"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DemoContractTests(unittest.TestCase):
    def test_acceptance_suite_rejects_broken_implementation(self):
        with tempfile.TemporaryDirectory() as scratch:
            project = Path(scratch) / "project"
            shutil.copytree(
                ROOT / "examples" / "dedupe-demo", project,
                ignore=shutil.ignore_patterns("__pycache__", "runs"),
            )
            (project / "src" / "merge.py").write_text(
                "def merge_records(existing, incoming):\n    return existing + incoming\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
                cwd=str(project), capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("test_same_input_twice_is_idempotent", result.stderr)
            self.assertIn("test_invalid_ids_raise_value_error", result.stderr)
            self.assertIn("Ran 9 tests", result.stderr)
            self.assertIn("FAILED", result.stderr)


if __name__ == "__main__":
    unittest.main()
