"""Background job manager for the Streamlit UI.

The pipeline runs as a subprocess (ui/pipeline_main.py) so the Streamlit
server never blocks. Job state lives on disk under artifacts/.ui_jobs so
it survives Streamlit script reruns. One job at a time (lock by pid).
"""
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_DIR = REPO_ROOT / "ui"
JOBS_DIR = REPO_ROOT / "artifacts" / ".ui_jobs"

STATE_FILE = JOBS_DIR / "current.json"
EXIT_MARKER = "__GLOSSAPI_UI_EXIT__="


def _ensure_dirs() -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def _load_state():
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_state(job: dict) -> None:
    _ensure_dirs()
    STATE_FILE.write_text(json.dumps(job, indent=2), encoding="utf-8")


def _pid_alive(pid: int) -> bool:
    """Is `pid` a live process? Also reaps zombie children of this process.

    A finished subprocess.Popen stays a zombie (defunct) until reaped, and
    os.kill(pid, 0) still succeeds on zombies — which would make a completed
    job look 'running' forever. os.waitpid(WNOHANG) reaps our own dead
    children and raises ChildProcessError for non-children.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        waited, _ = os.waitpid(pid, os.WNOHANG)
        return waited == 0  # 0 -> child still running; pid -> reaped zombie
    except ChildProcessError:
        return True  # not our child; the kill() above proved it exists



def tail_text(log_path: Path, max_chars: int = 20000) -> str:
    if not log_path.exists():
        return ""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    return text[-max_chars:]


def _final_exit_code(log_text: str):
    for line in reversed(log_text.splitlines()):
        line = line.strip()
        if line.startswith(EXIT_MARKER):
            try:
                return int(line[len(EXIT_MARKER):])
            except ValueError:
                return None
    return None


def status() -> dict:
    """Current job status: state in {idle, running, done, failed}."""
    job = _load_state()
    if job is None:
        return {"state": "idle"}
    log = tail_text(Path(job["log"]))
    running = _pid_alive(int(job["pid"]))
    if running:
        return {"state": "running", "job": job, "log": log}
    code = _final_exit_code(log)
    if code == 0:
        return {"state": "done", "job": job, "log": log}
    if code is not None:
        return {"state": "failed", "job": job, "log": log}
    # pid dead with no exit marker: killed / crashed hard
    return {"state": "failed", "job": job, "log": log,
            "note": "process ended without an exit marker (killed or crashed)"}


def start_job(in_dir: Path, artifacts_dir: Path, backend: str = "auto",
              fix_headings: bool = False) -> dict:
    """Launch the pipeline subprocess. Returns the job dict.

    Raises RuntimeError if a job is already running.
    """
    cur = status()
    if cur["state"] == "running":
        raise RuntimeError("A pipeline job is already running.")

    _ensure_dirs()
    job_id = time.strftime("%Y%m%d_%H%M%S")
    log_path = JOBS_DIR / f"job_{job_id}.log"

    cmd = [
        sys.executable, "-u", str(UI_DIR / "pipeline_main.py"),
        str(in_dir), str(artifacts_dir), backend,
    ]
    if fix_headings:
        cmd.append("--fix-headings")
    proc = subprocess.Popen(
        cmd,
        stdout=open(log_path, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
        start_new_session=True,  # survive the Streamlit process exiting
    )
    job = {
        "id": job_id,
        "pid": proc.pid,
        "in_dir": str(in_dir),
        "artifacts_dir": str(artifacts_dir),
        "backend": backend,
        "fix_headings": fix_headings,
        "log": str(log_path),
        "started": time.time(),
    }
    _save_state(job)
    return job


def run_tool(args, timeout: int = 600) -> tuple:
    """Run a repo helper script and capture its output. Returns (code, text)."""
    cmd = [sys.executable, "-u"] + [str(a) for a in args]
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, f"Timed out after {timeout}s: {shlex.join(cmd)}"


def cancel_job() -> bool:
    """Terminate the running pipeline job (whole process group)."""
    job = _load_state()
    if job is None:
        return False
    pid = int(job["pid"])
    if _pid_alive(pid):
        try:
            os.killpg(os.getpgid(pid), 15)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
    return True


def clear_finished_job() -> None:

    """Forget the current job so a new one can start."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
