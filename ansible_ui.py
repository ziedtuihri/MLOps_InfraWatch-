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
<html lang="en" data-theme="dark">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InfraWatch · Workflow Runner</title>
  <style>
    :root {
      --bg: #0d1117;
      --panel: #151b25;
      --panel-2: #1a2230;
      --border: #252e3d;
      --tx: #e8ecf3;
      --tx-2: #aab3c2;
      --tx-muted: #6f7a8c;
      --accent: #19d3a6;
      --accent-bg: rgba(25, 211, 166, .10);
      --ok: #2fd27f;
      --warn: #f5a524;
      --crit: #f05252;
      --term-bg: #0a0e14;
      --shadow: 0 8px 28px rgba(0, 0, 0, .35);
      font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    [data-theme="light"] {
      --bg: #f2f5f9;
      --panel: #ffffff;
      --panel-2: #f6f8fb;
      --border: #dde3ec;
      --tx: #18202e;
      --tx-2: #44506a;
      --tx-muted: #7b8698;
      --accent: #0aa985;
      --accent-bg: rgba(10, 169, 133, .09);
      --ok: #1a9f5c;
      --warn: #c98108;
      --crit: #d63b3b;
      --term-bg: #f6f8fb;
      --shadow: 0 6px 22px rgba(20, 35, 60, .08);
    }

    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--tx); min-height: 100vh; }

    /* ── top bar ── */
    .topnav {
      display: flex; align-items: center; gap: 12px;
      padding: 0 28px; height: 56px;
      background: var(--panel); border-bottom: 1px solid var(--border);
      position: sticky; top: 0; z-index: 5;
    }
    .logo { display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 16px; letter-spacing: .2px; }
    .logo-bar { width: 4px; height: 22px; border-radius: 2px; background: var(--accent); }
    .crumb { color: var(--tx-muted); font-size: 13px; }
    .spacer { flex: 1; }
    .theme-btn {
      background: transparent; color: var(--tx-2); border: 1px solid var(--border);
      border-radius: 20px; padding: 6px 14px; font: inherit; font-size: 12.5px; cursor: pointer;
      transition: all .15s;
    }
    .theme-btn:hover { border-color: var(--accent); color: var(--accent); }

    /* ── layout ── */
    .wrap { max-width: 1040px; margin: 0 auto; padding: 28px 20px 48px; }
    .title { font-size: 22px; font-weight: 650; margin: 0 0 4px; }
    .subtitle { color: var(--tx-muted); margin: 0 0 22px; font-size: 13.5px; }
    .grid { display: grid; grid-template-columns: 1fr 320px; gap: 18px; align-items: start; }
    @media (max-width: 860px) { .grid { grid-template-columns: 1fr; } }

    .card {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 12px; box-shadow: var(--shadow); overflow: hidden;
    }
    .card-head {
      display: flex; align-items: center; gap: 12px;
      padding: 14px 18px; border-bottom: 1px solid var(--border);
    }
    .card-title { font-weight: 600; font-size: 14.5px; }
    .card-body { padding: 18px; }

    .step-num {
      width: 26px; height: 26px; border-radius: 50%;
      background: var(--accent); color: #04261e; font-weight: 700; font-size: 13px;
      display: grid; place-items: center; flex-shrink: 0;
    }

    /* ── action bar ── */
    .actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 14px 18px; border-bottom: 1px solid var(--border); }
    .pill-btn {
      background: var(--panel-2); color: var(--tx); border: 1px solid var(--border);
      border-radius: 20px; padding: 6px 16px; font: inherit; font-size: 12.5px; font-weight: 600; cursor: pointer;
      transition: all .15s;
    }
    .pill-btn:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }
    .pill-btn:disabled { opacity: .45; cursor: not-allowed; }
    .count { margin-left: auto; font-size: 12px; color: var(--tx-muted); }

    /* ── step rows (same pattern as the resource list) ── */
    .step-list { display: flex; flex-direction: column; }
    .step {
      display: flex; align-items: center; gap: 14px;
      padding: 14px 18px; cursor: pointer; position: relative;
      border-bottom: 1px solid var(--border);
      transition: background .15s;
    }
    .step:last-child { border-bottom: 0; }
    .step:hover { background: var(--panel-2); }
    .step input { position: absolute; opacity: 0; pointer-events: none; }
    .step.selected { background: var(--accent-bg); }
    .step.selected::before { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--accent); }
    .step-icon {
      width: 38px; height: 38px; border-radius: 8px; flex-shrink: 0;
      background: var(--panel-2); border: 1px solid var(--border);
      display: grid; place-items: center; font-size: 17px;
    }
    .step-info { flex: 1; min-width: 0; }
    .step-name { font-weight: 600; font-size: 13.5px; }
    .step.selected .step-name { color: var(--accent); }
    .step-desc { font-size: 12px; color: var(--tx-muted); margin-top: 2px; }
    .tag {
      font: 600 10.5px/1 "Roboto Mono", ui-monospace, monospace; text-transform: uppercase; letter-spacing: .05em;
      color: var(--tx-muted); border: 1px solid var(--border); border-radius: 5px; padding: 4px 7px;
    }
    .check {
      width: 20px; height: 20px; border-radius: 5px; border: 1.5px solid var(--border);
      display: grid; place-items: center; font-size: 13px; font-weight: 700; color: transparent; flex-shrink: 0;
      transition: all .15s;
    }
    .step.selected .check { background: var(--accent); border-color: var(--accent); color: #04261e; }

    /* ── footer buttons ── */
    .footer { display: flex; gap: 10px; padding: 14px 18px; border-top: 1px solid var(--border); background: var(--panel-2); }
    .btn {
      border: 0; border-radius: 8px; padding: 10px 18px; font: inherit; font-weight: 650; font-size: 13.5px;
      cursor: pointer; transition: transform .1s, filter .15s, background .15s;
    }
    .btn:disabled { opacity: .45; cursor: not-allowed; }
    .btn-primary { background: var(--accent); color: #04261e; }
    .btn-primary:hover:not(:disabled) { filter: brightness(1.08); transform: translateY(-1px); }
    .btn-ghost { background: transparent; color: var(--tx); border: 1px solid var(--border); }
    .btn-ghost:hover:not(:disabled) { border-color: var(--accent); color: var(--accent); }

    /* ── MLflow card ── */
    .ml-icon {
      width: 42px; height: 42px; border-radius: 10px; background: var(--accent-bg);
      display: grid; place-items: center; font-size: 20px; margin-bottom: 12px;
    }
    .ml-card h3 { margin: 0 0 6px; font-size: 15px; }
    .ml-card p { margin: 0 0 16px; color: var(--tx-muted); font-size: 12.5px; }
    .ml-link {
      display: inline-flex; align-items: center; gap: 8px; text-decoration: none;
      background: var(--accent); color: #04261e; font-weight: 650; font-size: 13px;
      padding: 9px 16px; border-radius: 8px; transition: filter .15s, transform .1s;
    }
    .ml-link:hover { filter: brightness(1.08); transform: translateY(-1px); }

    /* ── status ── */
    .status-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .status-label { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--tx-muted); }
    .badge {
      display: inline-flex; align-items: center; gap: 7px;
      font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
      padding: 5px 12px; border-radius: 20px; border: 1px solid var(--border); color: var(--tx-2);
    }
    .badge .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--tx-muted); }
    .badge.run  { color: var(--accent); border-color: var(--accent); background: var(--accent-bg); }
    .badge.run .dot { background: var(--accent); animation: pulse 1.2s infinite; }
    .badge.queued { color: var(--warn); border-color: var(--warn); }
    .badge.queued .dot { background: var(--warn); animation: pulse 1.2s infinite; }
    .badge.ok   { color: var(--ok); border-color: var(--ok); background: rgba(47, 210, 127, .09); }
    .badge.ok .dot { background: var(--ok); }
    .badge.crit { color: var(--crit); border-color: var(--crit); background: rgba(240, 82, 82, .09); }
    .badge.crit .dot { background: var(--crit); }
    @keyframes pulse { 0%,100% { opacity: 1; transform: scale(1); } 50% { opacity: .35; transform: scale(.7); } }

    .progress { height: 3px; background: var(--border); overflow: hidden; display: none; }
    .progress.on { display: block; }
    .progress::after {
      content: ""; display: block; height: 100%; width: 35%; background: var(--accent);
      animation: slide 1.1s ease-in-out infinite;
    }
    @keyframes slide { 0% { margin-left: -35%; } 100% { margin-left: 100%; } }

    .error { color: var(--crit); font-size: 13px; margin: 10px 0 0; min-height: 1em; }

    /* ── terminal ── */
    .term-wrap { margin-top: 18px; }
    .term-bar { display: flex; align-items: center; gap: 7px; padding: 11px 16px; border-bottom: 1px solid var(--border); }
    .term-dot { width: 10px; height: 10px; border-radius: 50%; }
    .term-title { margin-left: 8px; font-size: 12px; color: var(--tx-muted); font-family: "Roboto Mono", ui-monospace, monospace; }
    pre#output {
      margin: 0; padding: 16px 18px; min-height: 14rem; max-height: 56vh; overflow: auto;
      background: var(--term-bg); color: var(--tx-2);
      font: 12.5px/1.65 "Roboto Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
      white-space: pre-wrap; word-break: break-word;
    }
    pre#output .l-play { color: var(--accent); font-weight: 700; }
    pre#output .l-ok { color: var(--ok); }
    pre#output .l-changed { color: var(--warn); }
    pre#output .l-bad { color: var(--crit); font-weight: 600; }
    pre#output .l-dim { color: var(--tx-muted); }
    pre#output::-webkit-scrollbar { width: 10px; height: 10px; }
    pre#output::-webkit-scrollbar-thumb { background: var(--border); border-radius: 6px; }
  </style>
</head>
<body>
  <header class="topnav">
    <div class="logo"><div class="logo-bar"></div><span>InfraWatch</span></div>
    <span class="crumb">/ Workflow Runner</span>
    <div class="spacer"></div>
    <button class="theme-btn" id="theme-btn" type="button">Light</button>
  </header>

  <main class="wrap">
    <h1 class="title">Ansible Workflow Runner</h1>
    <p class="subtitle">Runs the local playbook. Only the steps you select can be started.</p>

    <div class="grid">
      <!-- LEFT: steps -->
      <form id="run-form" class="card" autocomplete="off">
        <div class="card-head">
          <div class="step-num">1</div>
          <div class="card-title">Select workflow steps</div>
        </div>

        <div class="actions">
          <button type="button" class="pill-btn" id="select-all">Select All</button>
          <button type="button" class="pill-btn" id="clear-all">Clear</button>
          <span class="count" id="count">0 selected</span>
        </div>

        <div class="step-list">
          <label class="step">
            <input type="checkbox" name="tag" value="setup">
            <div class="step-icon">&#128230;</div>
            <div class="step-info"><div class="step-name">Setup</div><div class="step-desc">Install dependencies</div></div>
            <span class="tag">setup</span><div class="check">&#10003;</div>
          </label>
          <label class="step">
            <input type="checkbox" name="tag" value="stack">
            <div class="step-icon">&#128051;</div>
            <div class="step-info"><div class="step-name">Stack</div><div class="step-desc">Start Compose and wait for MLflow</div></div>
            <span class="tag">stack</span><div class="check">&#10003;</div>
          </label>
          <label class="step">
            <input type="checkbox" name="tag" value="quality">
            <div class="step-icon">&#128737;</div>
            <div class="step-info"><div class="step-name">Quality</div><div class="step-desc">Formatting, lint, security</div></div>
            <span class="tag">quality</span><div class="check">&#10003;</div>
          </label>
          <label class="step">
            <input type="checkbox" name="tag" value="tests">
            <div class="step-icon">&#129514;</div>
            <div class="step-info"><div class="step-name">Tests</div><div class="step-desc">Run pytest</div></div>
            <span class="tag">tests</span><div class="check">&#10003;</div>
          </label>
          <label class="step">
            <input type="checkbox" name="tag" value="training">
            <div class="step-icon">&#129504;</div>
            <div class="step-info"><div class="step-name">Training</div><div class="step-desc">Train models (also starts the stack)</div></div>
            <span class="tag">training</span><div class="check">&#10003;</div>
          </label>
        </div>

        <div class="footer">
          <button type="submit" class="btn btn-primary" id="run-selected">Run selected steps</button>
          <button type="button" class="btn btn-ghost" id="run-all">Run all steps</button>
        </div>
      </form>

      <!-- RIGHT: MLflow + status -->
      <div style="display:flex; flex-direction:column; gap:18px;">
        <div class="card ml-card">
          <div class="card-body">
            <div class="ml-icon">&#128202;</div>
            <h3>MLflow Tracking Server</h3>
            <p>Access your experiment tracking, artifacts, and model parameters.</p>
            <a class="ml-link" href="http://192.168.100.77:5000/" target="_blank" rel="noopener noreferrer">
              Launch MLflow UI <span>&rarr;</span>
            </a>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><div class="card-title">Run status</div></div>
          <div class="progress" id="progress"></div>
          <div class="card-body" aria-live="polite">
            <div class="status-row">
              <span class="status-label">Status</span>
              <span class="badge" id="status-badge"><span class="dot"></span><span id="status">Idle</span></span>
            </div>
            <p id="message" class="error"></p>
          </div>
        </div>
      </div>
    </div>

    <!-- OUTPUT -->
    <div class="card term-wrap">
      <div class="term-bar">
        <span class="term-dot" style="background:#f05252"></span>
        <span class="term-dot" style="background:#f5a524"></span>
        <span class="term-dot" style="background:#2fd27f"></span>
        <span class="term-title">ansible-output</span>
      </div>
      <pre id="output">Run output will appear here.</pre>
    </div>
  </main>

  <script>
    const form = document.querySelector("#run-form");
    const status = document.querySelector("#status");
    const badge = document.querySelector("#status-badge");
    const progress = document.querySelector("#progress");
    const output = document.querySelector("#output");
    const message = document.querySelector("#message");
    const countEl = document.querySelector("#count");
    const runAllBtn = document.querySelector("#run-all");
    const buttons = [
      document.querySelector("#run-selected"),
      runAllBtn,
      document.querySelector("#select-all"),
      document.querySelector("#clear-all")
    ];
    const rows = [...form.querySelectorAll(".step")];
    let currentRun = null;
    let lastOutput = null;

    /* ── theme ── */
    const themeBtn = document.querySelector("#theme-btn");
    function applyTheme(t) {
      document.documentElement.setAttribute("data-theme", t);
      themeBtn.textContent = t === "dark" ? "Light" : "Dark";
    }
    applyTheme(localStorage.getItem("wf-theme") || "dark");
    themeBtn.addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
      localStorage.setItem("wf-theme", next);
      applyTheme(next);
    });

    /* ── step selection ── */
    function syncRows() {
      let n = 0;
      rows.forEach(row => {
        const input = row.querySelector("input");
        row.classList.toggle("selected", input.checked);
        if (input.checked) n += 1;
      });
      countEl.textContent = n + " selected";
    }
    rows.forEach(row => row.querySelector("input").addEventListener("change", syncRows));
    document.querySelector("#select-all").addEventListener("click", () => {
      rows.forEach(row => { row.querySelector("input").checked = true; });
      syncRows();
    });
    document.querySelector("#clear-all").addEventListener("click", () => {
      rows.forEach(row => { row.querySelector("input").checked = false; });
      syncRows();
    });
    syncRows();

    /* ── status badge ── */
    function setStatus(text, kind) {
      status.textContent = text;
      badge.className = "badge" + (kind ? " " + kind : "");
      progress.classList.toggle("on", kind === "run" || kind === "queued");
    }
    function kindOf(data) {
      if (data.status === "queued") return "queued";
      if (data.status === "running") return "run";
      if (data.return_code === 0) return "ok";
      if (data.return_code !== null && data.return_code !== undefined) return "crit";
      return /fail|error/i.test(data.status || "") ? "crit" : "ok";
    }
    function statusText(data) {
      return data.status + (data.return_code === null || data.return_code === undefined ? "" : " (exit " + data.return_code + ")");
    }
    function setBusy(busy) {
      buttons.forEach(button => { button.disabled = busy; });
    }

    /* ── colored terminal output ── */
    function renderOutput(text) {
      if (text === lastOutput) return;
      lastOutput = text;
      const nearBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 60;
      const frag = document.createDocumentFragment();
      text.split("\\n").forEach((line, i, all) => {
        const span = document.createElement("span");
        if (/^(PLAY|TASK) \\[|^PLAY RECAP/.test(line)) span.className = "l-play";
        else if (/fatal:|FAILED|failed=[1-9]|unreachable=[1-9]|ERROR/.test(line)) span.className = "l-bad";
        else if (/^changed:|changed=[1-9]/.test(line)) span.className = "l-changed";
        else if (/^ok:|^skipping:/.test(line)) span.className = /^ok:/.test(line) ? "l-ok" : "l-dim";
        span.textContent = line + (i < all.length - 1 ? "\\n" : "");
        frag.appendChild(span);
      });
      output.replaceChildren(frag);
      if (nearBottom) output.scrollTop = output.scrollHeight;
    }

    /* ── API calls (unchanged endpoints) ── */
    async function startRun(tags) {
      message.textContent = "";
      lastOutput = null;
      renderOutput("Starting Ansible...");
      setStatus("Queued", "queued");
      setBusy(true);
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
        setStatus("Failed to start", "crit");
        message.textContent = error.message;
        setBusy(false);
      }
    }

    async function pollRun() {
      if (!currentRun) return;
      try {
        const response = await fetch("/api/runs/" + currentRun);
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Could not read run status.");
        }
        setStatus(statusText(data), kindOf(data));
        renderOutput(data.output || "Waiting for Ansible output...");
        if (data.status === "queued" || data.status === "running") {
          window.setTimeout(pollRun, 1000);
        } else {
          setBusy(false);
        }
      } catch (error) {
        setStatus("Error", "crit");
        message.textContent = error.message;
        setBusy(false);
      }
    }

    form.addEventListener("submit", event => {
      event.preventDefault();
      const tags = [...form.querySelectorAll('input[name="tag"]:checked')].map(item => item.value);
      if (!tags.length) {
        message.textContent = "Select at least one step, or use Run all steps.";
        return;
      }
      startRun(tags);
    });
    runAllBtn.addEventListener("click", () => startRun(null));

    /* restore the latest run after a page reload */
    (async () => {
      try {
        const response = await fetch("/api/runs/latest");
        if (response.status === 404) return;
        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || "Could not restore run status.");
        }
        currentRun = data.id;
        renderOutput(data.output || "Waiting for Ansible output...");
        setStatus(statusText(data), kindOf(data));
        if (data.status === "queued" || data.status === "running") {
          setBusy(true);
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