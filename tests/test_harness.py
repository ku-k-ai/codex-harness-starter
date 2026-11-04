"""ランナーの境界を、隔離した作業フォルダと実コマンドで検証する。"""

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tools" / "harness.py"


def check(check_id="verify", code="print('verified')", timeout=5):
    return {
        "id": check_id,
        "argv": ["{python}", "-c", code],
        "timeout_seconds": timeout,
    }


class HarnessTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory(prefix="codex harness test ")
        self.addCleanup(self.scratch.cleanup)
        self.target = Path(self.scratch.name) / "project with spaces"
        (self.target / "src").mkdir(parents=True)
        (self.target / "src" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
        (self.target / ".harness").mkdir()
        self.config_path = self.target / ".harness" / "checks.json"

    def config(self, checks=None, paths=None):
        return {
            "schema_version": 1,
            "checks": [check()] if checks is None else checks,
            "fingerprint_paths": ["src"] if paths is None else paths,
        }

    def save_config(self, config):
        self.config_path.write_text(json.dumps(config), encoding="utf-8")

    def invoke(self, command, label="candidate"):
        argv = [sys.executable, str(HARNESS), command, str(self.target)]
        if command == "run":
            argv += ["--label", label]
        return subprocess.run(argv, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=30)

    def output(self, result, expected_code):
        self.assertEqual(result.returncode, expected_code, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def report(self, result, expected_code):
        summary = self.output(result, expected_code)
        path = Path(summary["report"])
        return json.loads(path.read_text(encoding="utf-8")), path.parent

    def assert_rejected_before_execution(self, config):
        self.save_config(config)
        result = self.invoke("run")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stderr)["status"], "error")
        self.assertFalse((self.target / "executed.txt").exists())
        self.assertFalse((self.target / ".harness" / "runs").exists())

    def test_init_preserves_existing_files_and_agents(self):
        task = self.target / ".harness" / "TASK.md"
        task.write_text("keep this task\n", encoding="utf-8")
        agents = self.target / "AGENTS.md"
        agents.write_text("keep these instructions\n", encoding="utf-8")
        initialized = self.output(self.invoke("init"), 0)
        self.assertEqual(initialized["preserved"], ["TASK.md"])
        self.assertEqual(set(initialized["copied"]), {
            "STATE.md", "EXPERIMENTS.md", "AGENTS.fragment.md", "checks.json",
        })
        self.assertEqual(json.loads(self.config_path.read_text(encoding="utf-8"))["checks"], [])
        originals = {p.name: p.read_bytes() for p in (self.target / ".harness").iterdir()}
        repeated = self.output(self.invoke("init"), 0)
        self.assertEqual(repeated["copied"], [])
        self.assertEqual(set(repeated["preserved"]), set(originals))
        for name, content in originals.items():
            self.assertEqual((self.target / ".harness" / name).read_bytes(), content)
        self.assertEqual(task.read_text(encoding="utf-8"), "keep this task\n")
        self.assertEqual(agents.read_text(encoding="utf-8"), "keep these instructions\n")

    def test_unconfigured_template_cannot_pass(self):
        self.output(self.invoke("init"), 0)
        result = self.invoke("run")
        self.assertEqual(result.returncode, 2)
        self.assertIn("checks is empty", result.stderr)
        self.assertFalse((self.target / ".harness" / "runs").exists())

    def test_invalid_config_is_rejected_before_any_command(self):
        marker = check("first", "from pathlib import Path; Path('executed.txt').write_text('ran')")
        valid = self.config([marker, check("second")])
        cases = []
        for argv in ([], [""], ["   "], [None], ["TODO"], ["echo", "<command>"], ["{node}"]):
            cfg = copy.deepcopy(valid)
            cfg["checks"][1]["argv"] = argv
            cases.append(("argv=" + repr(argv), cfg))
        for timeout in (0, -1, True, None, "120", float("inf"), float("nan")):
            cfg = copy.deepcopy(valid)
            cfg["checks"][1]["timeout_seconds"] = timeout
            cases.append(("timeout=" + repr(timeout), cfg))
        for check_id in ("first", "FIRST", "../escape", "CON", "nul.txt"):
            cfg = copy.deepcopy(valid)
            cfg["checks"][1]["id"] = check_id
            cases.append(("id=" + check_id, cfg))
        for key, value in (("shell", True), ("env", {"EXAMPLE": "value"})):
            cfg = copy.deepcopy(valid)
            cfg["checks"][1][key] = value
            cases.append(("unsupported=" + key, cfg))
        for paths in ([], [""], ["TODO"], ["../outside"], ["/absolute"], ["C:/absolute"],
                      ["src\\main.py"], ["missing-source"], [".harness/runs"]):
            cfg = copy.deepcopy(valid)
            cfg["fingerprint_paths"] = paths
            cases.append(("paths=" + repr(paths), cfg))
        cfg = copy.deepcopy(valid)
        cfg["schema_version"] = True
        cases.append(("boolean schema", cfg))
        cases.append(("empty checks", self.config(checks=[])))
        for name, config in cases:
            with self.subTest(name=name):
                self.assert_rejected_before_execution(config)

    def test_empty_fingerprint_directory_is_rejected(self):
        (self.target / "empty").mkdir()
        self.assert_rejected_before_execution(self.config(paths=["empty"]))

    def test_pass_report_captures_outputs_and_fresh_status(self):
        code = "import sys; print('normal output'); print('diagnostic', file=sys.stderr)"
        self.save_config(self.config([check("output", code)]))
        report, directory = self.report(self.invoke("run", "baseline"), 0)
        self.assertEqual(report["label"], "baseline")
        self.assertEqual(report["scope"], "configured_checks_only")
        self.assertTrue(report["all_checks_passed"])
        self.assertFalse(report["source_changed_during_run"])
        self.assertEqual(report["fingerprinted_files"], ["src/main.py"])
        self.assertEqual(len(report["content_fingerprint"]), 64)
        self.assertEqual(len(report["config_fingerprint"]), 64)
        self.assertIn("started_at", report)
        self.assertIn("ended_at", report)
        self.assertIn("git", report)
        item = report["checks"][0]
        self.assertEqual(item["argv"][0], sys.executable)
        self.assertEqual(item["returncode"], 0)
        self.assertEqual((directory / item["stdout"]).read_text(encoding="utf-8"), "normal output\n")
        self.assertEqual((directory / item["stderr"]).read_text(encoding="utf-8"), "diagnostic\n")
        state = self.output(self.invoke("status"), 0)
        self.assertEqual(state["status"], "passed")
        self.assertFalse(state["stale"])

    def test_failure_does_not_skip_later_checks(self):
        self.save_config(self.config([
            check("first"), check("failure", "import sys; sys.exit(7)"),
            check("last", "from pathlib import Path; Path('executed.txt').write_text('ran')"),
        ]))
        report, _ = self.report(self.invoke("run"), 1)
        self.assertEqual([item["status"] for item in report["checks"]], ["passed", "failed", "passed"])
        self.assertEqual(report["checks"][1]["returncode"], 7)
        self.assertTrue((self.target / "executed.txt").exists())
        state = self.output(self.invoke("status"), 1)
        self.assertEqual(state["status"], "failed")
        self.assertFalse(state["stale"])

    def test_source_edit_marks_a_passing_report_stale(self):
        self.save_config(self.config())
        self.report(self.invoke("run"), 0)
        (self.target / "src" / "main.py").write_text("VALUE = 2\n", encoding="utf-8")
        state = self.output(self.invoke("status"), 1)
        self.assertTrue(state["all_checks_passed"])
        self.assertEqual(state["status"], "stale")
        self.assertIn("Source content changed since the run", state["reasons"])

    def test_changed_check_configuration_marks_report_stale(self):
        self.save_config(self.config())
        self.report(self.invoke("run"), 0)
        self.save_config(self.config([check("different-command")]))
        state = self.output(self.invoke("status"), 1)
        self.assertTrue(state["stale"])
        self.assertIn("Check configuration changed since the run", state["reasons"])

    def test_declared_task_is_tracked_but_work_log_is_not(self):
        task = self.target / ".harness" / "TASK.md"
        task.write_text("acceptance criteria\n", encoding="utf-8")
        self.save_config(self.config(paths=["src", ".harness/TASK.md"]))
        self.report(self.invoke("run"), 0)
        (self.target / ".harness" / "STATE.md").write_text("record latest observation\n", encoding="utf-8")
        self.output(self.invoke("status"), 0)
        task.write_text("changed acceptance criteria\n", encoding="utf-8")
        self.assertTrue(self.output(self.invoke("status"), 1)["stale"])

    def test_changed_source_during_command_cannot_get_fresh_pass(self):
        code = "from pathlib import Path; Path('src/main.py').write_text('VALUE = 2\\n')"
        self.save_config(self.config([check("mutate", code)]))
        report, _ = self.report(self.invoke("run"), 1)
        self.assertTrue(report["all_checks_passed"])
        self.assertTrue(report["source_changed_during_run"])
        self.assertEqual(report["status"], "failed")
        self.assertTrue(self.output(self.invoke("status"), 1)["stale"])

    def test_timeout_is_recorded_and_next_check_runs(self):
        self.save_config(self.config([
            check("slow", "import time; print('started', flush=True); time.sleep(10)", timeout=0.5),
            check("next"),
        ]))
        started = time.monotonic()
        report, directory = self.report(self.invoke("run"), 1)
        self.assertLess(time.monotonic() - started, 8)
        self.assertEqual([item["status"] for item in report["checks"]], ["timeout", "passed"])
        self.assertIn("started", (directory / report["checks"][0]["stdout"]).read_text(encoding="utf-8"))

    def test_missing_executable_is_distinct_and_next_check_runs(self):
        missing = check("missing")
        missing["argv"] = [str(self.target / "does-not-exist-executable")]
        self.save_config(self.config([missing, check("next")]))
        report, directory = self.report(self.invoke("run"), 1)
        self.assertEqual([item["status"] for item in report["checks"]], ["missing_executable", "passed"])
        self.assertIsNone(report["checks"][0]["returncode"])
        self.assertTrue((directory / report["checks"][0]["stderr"]).read_bytes())

    def test_external_symlink_scope_is_rejected_before_execution(self):
        external = Path(self.scratch.name) / "outside.txt"
        external.write_text("outside target", encoding="utf-8")
        try:
            (self.target / "src" / "external.txt").symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest("Creating symlinks is unavailable on this host")
        self.assert_rejected_before_execution(self.config([
            check("first", "from pathlib import Path; Path('executed.txt').write_text('ran')"),
        ]))

    def test_status_does_not_fall_back_to_older_pass_when_latest_run_is_incomplete(self):
        self.save_config(self.config())
        self.assertEqual(self.output(self.invoke("status"), 1)["status"], "no_report")
        self.report(self.invoke("run"), 0)
        self.assertEqual(self.output(self.invoke("status"), 0)["status"], "passed")
        incomplete = self.target / ".harness" / "runs" / "99999999-incomplete"
        incomplete.mkdir()
        (incomplete / "interrupted.stdout.txt").write_text("partial", encoding="utf-8")
        state = self.output(self.invoke("status"), 1)
        self.assertEqual(state["status"], "incomplete")
        self.assertTrue(state["stale"])
        self.assertEqual(Path(state["report"]), incomplete / "report.json")

    def test_corrupt_latest_report_is_an_error(self):
        self.save_config(self.config())
        _, directory = self.report(self.invoke("run"), 0)
        (directory / "report.json").write_text("{broken", encoding="utf-8")
        result = self.invoke("status")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cannot read latest report", result.stderr)


if __name__ == "__main__":
    unittest.main()
