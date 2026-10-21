import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

PROJECT_DIR = Path(__file__).resolve().parent
PLAYBOOK_PATH = PROJECT_DIR / "ansible" / "site.yml"
RunTag = Literal["setup", "quality", "training", "tests", "stack"]
MAX_OUTPUT_LENGTH = 100_000
MAX_RUN_HISTORY = 20

app = FastAPI(title="Ansible Workflow Runner")
runs: dict[str, dict[str, int | str | None]] = {}


class RunRequest(BaseModel):
    tags: list[RunTag] | None = None


def build_ansible_command(executable: str, tags: list[str] | None) -> list[str]:
    command = [executable, str(PLAYBOOK_PATH)]
    if tags is not None:
        command.extend(["--tags", ",".join(tags)])
    return command


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTML_PAGE


@app.post("/api/runs", status_code=202)
async def start_run(request: RunRequest):
    if request.tags == []:
        raise HTTPException(status_code=422, detail="Select at least one step.")

    executable = shutil.which("ansible-playbook")
    if executable is None:
        raise HTTPException(
            status_code=503,
            detail="ansible-playbook was not found on PATH. Install Ansible first.",
        )

    if any(run["status"] in {"queued", "running"} for run in runs.values()):
        raise HTTPException(
            status_code=409, detail="An Ansible playbook run is already in progress."
        )

    while len(runs) >= MAX_RUN_HISTORY:
        oldest_finished = next(
            (
                run_id
                for run_id, run in runs.items()
                if run["status"] not in {"queued", "running"}
            ),
            None,
        )
        if oldest_finished is None:
            break
        del runs[oldest_finished]

    run_id = uuid.uuid4().hex
    runs[run_id] = {
        "status": "queued",
        "return_code": None,
        "output": "",
    }
    asyncio.create_task(_run_playbook(run_id, executable, request.tags))
    return {"id": run_id, **runs[run_id]}


@app.get("/api/runs/latest")
async def get_latest_run():
    if not runs:
        raise HTTPException(status_code=404, detail="No playbook runs yet.")
    run_id = next(reversed(runs))
    return {"id": run_id, **runs[run_id]}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run = runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return {"id": run_id, **run}


async def _run_playbook(run_id: str, executable: str, tags: list[str] | None):
    run = runs[run_id]
    try:
        process = await asyncio.create_subprocess_exec(
            *build_ansible_command(executable, tags),
            cwd=PROJECT_DIR,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        run["status"] = "failed"
        run["output"] = f"Could not start Ansible: {exc}"
        return

    run["status"] = "running"
    if process.stdout is None:
        process.kill()
        await process.wait()
        run["status"] = "failed"
        run["output"] = "Could not capture Ansible output."
        return

    async for line in process.stdout:
        output = str(run["output"]) + line.decode(errors="replace")
        run["output"] = output[-MAX_OUTPUT_LENGTH:]

    return_code = await process.wait()
    run["return_code"] = return_code
    run["status"] = "succeeded" if return_code == 0 else "failed"


HTML_PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ansible Workflow Runner</title>
  <style>
    :root { color-scheme: light dark; font: 16px system-ui, sans-serif; }
    body { max-width: 900px; margin: 3rem auto; padding: 0 1rem; }
    h1 { margin-bottom: .4rem; }
    .hint { opacity: .75; }
    form, section {
      border: 1px solid #8886;
      border-radius: 10px;
      padding: 1.25rem;
    }
    label { display: block; margin: .8rem 0; }
    input { margin-right: .5rem; }
    button {
      padding: .65rem 1rem;
      margin: .7rem .5rem 0 0;
      cursor: pointer;
    }
    #status { font-weight: 650; }
    pre { min-height: 10rem; max-height: 55vh; overflow: auto; padding: 1rem;
          border-radius: 8px; background: #8882; white-space: pre-wrap; }
    .error { color: #c33; }
  </style>
</head>
<body>
  <h1>Ansible Workflow Runner</h1>
  <p class="hint">
    Runs the local playbook. Only the steps selected below can be started.
  </p>
  <form id="run-form">
    <label><input type="checkbox" name="tag" value="setup">
      Setup — install dependencies</label>
    <label><input type="checkbox" name="tag" value="stack">
      Stack — start Compose and wait for MLflow</label>
    <label><input type="checkbox" name="tag" value="quality">
      Quality — formatting, lint, security</label>
    <label><input type="checkbox" name="tag" value="tests"> Tests — run pytest</label>
    <label><input type="checkbox" name="tag" value="training">
      Training — train models (also starts the stack)</label>
    <button type="submit">Run selected steps</button>
    <button type="button" id="run-all">Run all steps</button>
  </form>
  <section aria-live="polite" style="margin-top: 1.25rem">
    <div>Status: <span id="status">Idle</span></div>
    <p id="message" class="error"></p>
    <pre id="output">Run output will appear here.</pre>
  </section>
  <script>
    const form = document.querySelector("#run-form");
    const status = document.querySelector("#status");
    const output = document.querySelector("#output");
    const message = document.querySelector("#message");
    const buttons = [
      ...form.querySelectorAll("button"),
      document.querySelector("#run-all")
    ];
    let currentRun = null;

    async function startRun(tags) {
      message.textContent = "";
      output.textContent = "Starting Ansible...";
      status.textContent = "Queued";
      buttons.forEach(button => button.disabled = true);
      try {
        const response = await fetch("/api/runs", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({tags})
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "Could not start the run.");
        currentRun = data.id;
        await pollRun();
      } catch (error) {
        status.textContent = "Failed to start";
        message.textContent = error.message;
        buttons.forEach(button => button.disabled = false);
      }
    }

    async function pollRun() {
      if (!currentRun) return;
      try {
        const response = await fetch(`/api/runs/${currentRun}`);
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Could not read run status.");
        }
        status.textContent = data.status + (
          data.return_code === null ? "" : ` (exit ${data.return_code})`
        );
        output.textContent = data.output || "Waiting for Ansible output...";
        output.scrollTop = output.scrollHeight;
        if (data.status === "queued" || data.status === "running") {
          window.setTimeout(pollRun, 1000);
        } else {
          buttons.forEach(button => button.disabled = false);
        }
      } catch (error) {
        status.textContent = "Error";
        message.textContent = error.message;
        buttons.forEach(button => button.disabled = false);
      }
    }

    form.addEventListener("submit", event => {
      event.preventDefault();
      const tags = [
        ...form.querySelectorAll('input[name="tag"]:checked')
      ].map(item => item.value);
      startRun(tags);
    });
    document.querySelector("#run-all").addEventListener("click", () => startRun(null));

    (async () => {
      try {
        const response = await fetch("/api/runs/latest");
        if (response.status === 404) return;
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Could not restore run status.");
        }
        currentRun = data.id;
        output.textContent = data.output || "Waiting for Ansible output...";
        status.textContent = data.status + (
          data.return_code === null ? "" : ` (exit ${data.return_code})`
        );
        if (data.status === "queued" || data.status === "running") {
          buttons.forEach(button => button.disabled = true);
          await pollRun();
        }
      } catch (error) {
        message.textContent = error.message;
      }
    })();
  </script>
</body>
</html>
"""
