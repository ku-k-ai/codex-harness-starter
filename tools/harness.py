#!/usr/bin/env python3
"""Run explicit checks and bind their evidence to local source content.

Python 3.9+, standard library only. A passing report verifies the configured
commands; it is not a declaration that the user's business goal is complete.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
import uuid

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"
TEMPLATES = {
    "TASK.md": "TASK.md",
    "STATE.md": "STATE.md",
    "EXPERIMENTS.md": "EXPERIMENTS.md",
    "AGENTS.fragment.md": "AGENTS.fragment.md",
    "checks.example.json": "checks.json",
}
IGNORED_DIRS = {".git", ".harness", "__pycache__", ".pytest_cache"}
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|REPLACE_ME|CHANGE_ME|YOUR_COMMAND)\b", re.I)


class HarnessError(Exception):
    """Configuration or evidence could not be safely inspected."""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def target_directory(value):
    target = Path(value).expanduser().resolve()
    if not target.is_dir():
        raise HarnessError("Target must be an existing directory: %s" % target)
    return target


def inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def managed_path(target, *parts):
    """Keep configuration and reports inside a real .harness directory."""
    path = target
    for part in (".harness",) + parts:
        path = path / part
        if path.is_symlink():
            raise HarnessError("Symlinks are not allowed in .harness paths: %s" % path)
    if not inside(path.resolve(), target):
        raise HarnessError("Path escapes the target: %s" % path)
    return path


def reject_constant(value):
    raise ValueError("Non-finite JSON number: %s" % value)


def read_config(target):
    path = managed_path(target, "checks.json")
    try:
        raw = path.read_bytes()
        cfg = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
    except (OSError, ValueError, UnicodeError) as exc:
        raise HarnessError("Cannot read .harness/checks.json: %s" % exc)
    if not isinstance(cfg, dict) or set(cfg) != {"schema_version", "checks", "fingerprint_paths"}:
        raise HarnessError("Config requires only schema_version, checks, and fingerprint_paths")
    if type(cfg["schema_version"]) is not int or cfg["schema_version"] != 1:
        raise HarnessError("schema_version must be 1")
    checks = cfg["checks"]
    if not isinstance(checks, list) or not checks:
        raise HarnessError("checks is empty: configure real verification commands first")
    ids = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != {"id", "argv", "timeout_seconds"}:
            raise HarnessError("Each check requires only id, argv, and timeout_seconds")
        check_id = check["id"]
        if not isinstance(check_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", check_id):
            raise HarnessError("Check id must be 1-64 letters, digits, dots, underscores, or hyphens")
        if check_id.casefold() in ids:
            raise HarnessError("Duplicate check id: %s" % check_id)
        if re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])", check_id.split(".")[0], re.I):
            raise HarnessError("Check id is a reserved Windows filename: %s" % check_id)
        ids.add(check_id.casefold())
        argv = check["argv"]
        if not isinstance(argv, list) or not argv:
            raise HarnessError("argv must be a nonempty string array: %s" % check_id)
        for arg in argv:
            if not isinstance(arg, str) or not arg.strip() or "\x00" in arg:
                raise HarnessError("argv contains an empty or invalid argument: %s" % check_id)
            if PLACEHOLDER.search(arg) or re.fullmatch(r"<[^>]+>", arg.strip()):
                raise HarnessError("argv contains an unfinished placeholder: %s" % check_id)
            if re.fullmatch(r"\{[A-Za-z_][A-Za-z0-9_]*\}", arg) and arg != "{python}":
                raise HarnessError("Only the {python} placeholder is supported: %s" % check_id)
        timeout = check["timeout_seconds"]
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
            raise HarnessError("timeout_seconds must be a finite positive number: %s" % check_id)
    paths = cfg["fingerprint_paths"]
    if not isinstance(paths, list) or not paths:
        raise HarnessError("fingerprint_paths must be a nonempty array")
    for item in paths:
        if not isinstance(item, str) or not item.strip() or "\x00" in item or PLACEHOLDER.search(item):
            raise HarnessError("fingerprint_paths contains an empty or unfinished path")
        # Accept portable relative paths only, even when this runner is on POSIX.
        if Path(item).is_absolute() or re.match(r"^[A-Za-z]:", item) or "\\" in item:
            raise HarnessError("Use relative paths with forward slashes: %s" % item)
        parts = Path(item).parts
        if (".." in parts or any(part in (IGNORED_DIRS - {".harness"}) for part in parts)
                or parts[:2] == (".harness", "runs")):
            raise HarnessError("Fingerprint path is outside the source scope: %s" % item)
    return cfg, hashlib.sha256(raw).hexdigest()


def fingerprint(target, paths):
    """Hash declared file names and bytes; reject external links and link cycles."""
    files = {}

    def visit(path, ancestors):
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise HarnessError("Cannot resolve fingerprint path %s: %s" % (path, exc))
        if not inside(resolved, target):
            raise HarnessError("Fingerprint path or symlink escapes target: %s" % path)
        parts = resolved.relative_to(target).parts
        if (any(part in (IGNORED_DIRS - {".harness"}) for part in parts)
                or parts[:2] == (".harness", "runs")):
            raise HarnessError("Fingerprint symlink points to excluded data: %s" % path)
        if path.is_dir():
            if resolved in ancestors:
                raise HarnessError("Fingerprint symlink cycle: %s" % path)
            try:
                entries = sorted(path.iterdir(), key=lambda p: p.name)
            except OSError as exc:
                raise HarnessError("Cannot list fingerprint directory: %s" % exc)
            for child in entries:
                if (child.name not in IGNORED_DIRS and child.suffix not in {".pyc", ".pyo"}
                        and child.relative_to(target).parts[:2] != (".harness", "runs")):
                    visit(child, ancestors | {resolved})
        elif path.is_file():
            digest = hashlib.sha256()
            try:
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(131072), b""):
                        digest.update(chunk)
            except OSError as exc:
                raise HarnessError("Cannot hash source file: %s" % exc)
            files[path.relative_to(target).as_posix()] = digest.hexdigest()
        else:
            raise HarnessError("Fingerprint path is not a regular file or directory: %s" % path)

    for relative in paths:
        visit(target / relative, set())
    if not files:
        raise HarnessError("Fingerprint scope has no regular source files")
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest(), sorted(files)


def initialize(target):
    missing = [name for name in TEMPLATES if not (TEMPLATE_DIR / name).is_file()]
    if missing:
        raise HarnessError("Missing starter templates: %s" % ", ".join(missing))
    managed_path(target).mkdir(exist_ok=True)
    copied, kept = [], []
    for source, destination in TEMPLATES.items():
        out = managed_path(target, destination)
        try:
            with out.open("xb") as stream:
                stream.write((TEMPLATE_DIR / source).read_bytes())
            copied.append(destination)
        except FileExistsError:
            kept.append(destination)
    emit({"status": "initialized", "copied": copied, "preserved": kept,
          "note": "AGENTS.md is unchanged. Configure checks.json before running."})
    return 0


def git_snapshot(target):
    if shutil.which("git") is None:
        return None
    prefix = ["git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", str(target)]
    try:
        head = subprocess.run(prefix + ["rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=5, check=False)
        if head.returncode != 0:
            return None
        state = subprocess.run(prefix + ["status", "--porcelain"], capture_output=True,
                               text=True, timeout=5, check=False)
        return {"head": head.stdout.strip(),
                "dirty": bool(state.stdout) if state.returncode == 0 else None}
    except (OSError, subprocess.TimeoutExpired):
        return None


def terminate_check(process):
    # Only touch the process (and process group/tree) started by this runner.
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def execute_check(target, directory, check):
    argv = [sys.executable if arg == "{python}" else arg for arg in check["argv"]]
    result = {"id": check["id"], "argv": argv, "timeout_seconds": check["timeout_seconds"],
              "started_at": now(), "returncode": None,
              "stdout": check["id"] + ".stdout.txt", "stderr": check["id"] + ".stderr.txt"}
    started = time.monotonic()
    with (directory / result["stdout"]).open("wb") as out, (directory / result["stderr"]).open("wb") as err:
        try:
            options = {"start_new_session": True} if os.name != "nt" else {
                "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
            process = subprocess.Popen(argv, cwd=str(target), stdout=out, stderr=err,
                                       shell=False, **options)
            try:
                result["returncode"] = process.wait(timeout=check["timeout_seconds"])
                result["status"] = "passed" if result["returncode"] == 0 else "failed"
            except subprocess.TimeoutExpired:
                terminate_check(process)
                result["status"] = "timeout"
                result["returncode"] = process.returncode
            except KeyboardInterrupt:
                terminate_check(process)
                raise
        except FileNotFoundError as exc:
            result["status"] = "missing_executable"
            err.write(str(exc).encode("utf-8", errors="replace"))
        except OSError as exc:
            result["status"] = "execution_error"
            err.write(str(exc).encode("utf-8", errors="replace"))
    result["ended_at"] = now()
    result["duration_seconds"] = round(time.monotonic() - started, 3)
    return result


def run_checks(target, label):
    cfg, cfg_hash = read_config(target)
    source_hash, files = fingerprint(target, cfg["fingerprint_paths"])
    # Validate everything above before any configured command can run.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ") + "-" + label + "-" + uuid.uuid4().hex[:8]
    directory = managed_path(target, "runs", run_id)
    directory.mkdir(parents=True, exist_ok=False)
    report = {"schema_version": 1, "run_id": run_id, "label": label,
              "scope": "configured_checks_only", "started_at": now(), "target": str(target),
              "content_fingerprint": source_hash, "config_fingerprint": cfg_hash,
              "fingerprinted_files": files, "git": git_snapshot(target)}
    report["checks"] = [execute_check(target, directory, check) for check in cfg["checks"]]
    report["all_checks_passed"] = all(check["status"] == "passed" for check in report["checks"])
    report["source_changed_during_run"] = False
    report["configuration_changed_during_run"] = False
    report["verification_error"] = None
    try:
        end_hash, _ = fingerprint(target, cfg["fingerprint_paths"])
        report["source_changed_during_run"] = end_hash != source_hash
        _, end_cfg_hash = read_config(target)
        report["configuration_changed_during_run"] = end_cfg_hash != cfg_hash
    except HarnessError as exc:
        report["verification_error"] = str(exc)
    stable = not (report["source_changed_during_run"] or report["configuration_changed_during_run"]
                  or report["verification_error"])
    report["status"] = "passed" if report["all_checks_passed"] and stable else "failed"
    report["ended_at"] = now()
    report_file = directory / "report.json"
    temporary = directory / "report.json.tmp"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(report_file)
    emit({"status": report["status"], "scope": report["scope"], "report": str(report_file),
          "all_checks_passed": report["all_checks_passed"], "source_stable": stable,
          "checks": [{"id": check["id"], "status": check["status"]} for check in report["checks"]]})
    return 0 if report["status"] == "passed" else 1


def latest_report(target):
    runs = managed_path(target, "runs")
    if not runs.exists():
        return None
    if not runs.is_dir():
        raise HarnessError(".harness/runs must be a directory")
    reports = []
    for directory in runs.iterdir():
        if directory.is_symlink():
            raise HarnessError("Symlinks are not allowed in report directories")
        if directory.is_dir():
            path = managed_path(target, "runs", directory.name, "report.json")
            reports.append(path)
    return max(reports, key=lambda path: path.parent.name) if reports else None


def status(target):
    cfg, cfg_hash = read_config(target)
    source_hash, _ = fingerprint(target, cfg["fingerprint_paths"])
    path = latest_report(target)
    if path is None:
        emit({"status": "no_report", "stale": True, "reasons": ["No run found"]})
        return 1
    if not path.exists():
        emit({"status": "incomplete", "scope": "configured_checks_only",
              "report": str(path), "stale": True,
              "reasons": ["Latest run has no completed report (interrupted or still running)"]})
        return 1
    try:
        report = json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)
        required = {"schema_version", "status", "all_checks_passed", "content_fingerprint",
                    "config_fingerprint", "checks", "source_changed_during_run",
                    "configuration_changed_during_run", "verification_error"}
        if not isinstance(report, dict) or not required <= set(report) or report["schema_version"] != 1:
            raise ValueError("unrecognized report schema")
        if type(report["all_checks_passed"]) is not bool or not isinstance(report["checks"], list) or not report["checks"]:
            raise ValueError("invalid check results")
        check_ids = [check["id"] for check in report["checks"]]
        if check_ids != [check["id"] for check in cfg["checks"]]:
            # A changed config is reported as stale below, rather than trusted.
            if report["config_fingerprint"] == cfg_hash:
                raise ValueError("check results do not match configuration")
        all_passed = all(check["status"] == "passed" for check in report["checks"])
        if all_passed != report["all_checks_passed"]:
            raise ValueError("inconsistent check summary")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HarnessError("Cannot read latest report: %s" % exc)
    reasons = []
    if report["content_fingerprint"] != source_hash:
        reasons.append("Source content changed since the run")
    if report["config_fingerprint"] != cfg_hash:
        reasons.append("Check configuration changed since the run")
    if report["source_changed_during_run"] or report["configuration_changed_during_run"]:
        reasons.append("Source or check configuration changed during the run")
    if report["verification_error"]:
        reasons.append("The run could not verify its final source/configuration state")
    fresh_pass = not reasons and all_passed and report["status"] == "passed"
    emit({"status": "stale" if reasons else ("passed" if fresh_pass else "failed"),
          "scope": "configured_checks_only", "report": str(path), "stale": bool(reasons),
          "all_checks_passed": all_passed, "reasons": reasons,
          "checks": [{"id": check["id"], "status": check["status"]} for check in report["checks"]]})
    return 0 if fresh_pass else 1


def doctor(target):
    result = {"python": sys.version.split()[0], "python_executable": sys.executable,
              "codex": "not found", "configuration": "invalid"}
    executable = shutil.which("codex")
    if executable:
        try:
            version = subprocess.run([executable, "--version"], capture_output=True,
                                     text=True, timeout=10, check=False)
            result["codex"] = version.stdout.strip() if version.returncode == 0 else "version command failed"
        except (OSError, subprocess.TimeoutExpired):
            result["codex"] = "version command unavailable"
    try:
        cfg, _ = read_config(target)
        _, files = fingerprint(target, cfg["fingerprint_paths"])
        result["configuration"] = "valid"
        result["checks"] = len(cfg["checks"])
        result["fingerprinted_files"] = len(files)
        code = 0
    except HarnessError as exc:
        result["configuration_error"] = str(exc)
        code = 2
    emit(result)
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "run", "status", "doctor"):
        item = sub.add_parser(command)
        item.add_argument("target", help="Existing target repository/directory")
        if command == "run":
            item.add_argument("--label", choices=("baseline", "candidate"), required=True)
    args = parser.parse_args(argv)
    try:
        target = target_directory(args.target)
        if args.command == "run":
            return run_checks(target, args.label)
        return {"init": initialize, "status": status, "doctor": doctor}[args.command](target)
    except (HarnessError, OSError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted; no new completed report was saved.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
