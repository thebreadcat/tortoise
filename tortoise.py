#!/usr/bin/env python3
"""
Tortoise — chunk-based coding harness for slow, small, local AI models.
Zero dependencies beyond Python stdlib.
Works with any OpenAI-compatible endpoint (Ollama, LiteLLM, OpenAI, etc.)

Usage:
    python3 tortoise.py init
    python3 tortoise.py add "build user login"
    python3 tortoise.py run
"""

import os, sys, re, json, shutil, difflib, argparse, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

VERSION = "0.2.1"

# ── Paths ──────────────────────────────────────────────────────────────────────

T           = ".tortoise"
BRAIN       = f"{T}/BRAIN.md"
CONSTITUTION = f"{T}/CONSTITUTION.md"
TODO        = f"{T}/TODO.md"
PROGRESS    = f"{T}/PROGRESS.md"
DECISIONS   = f"{T}/DECISIONS.md"
CURRENT     = f"{T}/CURRENT.md"
CONFIG      = f"{T}/config.json"
CHUNKS_DIR  = f"{T}/chunks"
BACKUP_DIR  = f"{T}/backups"
STOP_FILE   = f"{T}/STOP"

# ── Defaults ───────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "endpoint":      "http://localhost:11434/v1",
    "model":         "phi3",
    "max_tokens":    1500,
    "context_limit": 3000,
    "confirm_writes": True,
    "backup":        True,
    "max_files":     3,
    "exclude":       ["node_modules",".git","venv","__pycache__",
                      ".tortoise","dist","build",".DS_Store"]
}

BRAIN_INIT = """\
# Project Brain

## What this project is
[Describe the project in 2-3 sentences]

## Architecture
[Key directories and what they do]

## Current State
Not started.

## Known Issues
None yet.

## Do Not Touch
Nothing flagged yet.
"""

TODO_INIT = """\
## NOW
[Tortoise moves the active task here]

## NEXT
- [ ] [Add your first task here — or run: tortoise plan "your goal"]

## LATER

## BLOCKED

## DONE
"""

# ── Terminal colors (graceful fallback) ────────────────────────────────────────

def _c(t, code): return f"\033[{code}m{t}\033[0m" if sys.stdout.isatty() else t
def green(t):  return _c(t, "32")
def yellow(t): return _c(t, "33")
def red(t):    return _c(t, "31")
def cyan(t):   return _c(t, "36")
def bold(t):   return _c(t, "1")
def dim(t):    return _c(t, "2")

def ok(msg):   print(f"  {green('✓')} {msg}")
def info(msg): print(f"  {cyan('→')} {msg}")
def warn(msg): print(f"  {yellow('!')} {msg}")
def err(msg):  print(f"  {red('✗')} {msg}")
def head(msg): print(f"\n{bold(msg)}\n")

def confirm(prompt):
    try:
        return input(f"  {yellow('?')} {prompt} [y/N] ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False

# ── Config ─────────────────────────────────────────────────────────────────────

def load_cfg():
    cfg = DEFAULT_CONFIG.copy()
    if Path(CONFIG).exists():
        cfg.update(json.loads(Path(CONFIG).read_text()))
    return cfg

def save_cfg(cfg):
    Path(CONFIG).write_text(json.dumps(cfg, indent=2))

# ── File helpers ───────────────────────────────────────────────────────────────

def read(path, default=""):
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.exists() else default

def write(path, content):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")

# ── TODO management ────────────────────────────────────────────────────────────

def _tasks_in_section(section: str) -> list:
    """Unchecked tasks under a TODO section (e.g. NOW or NEXT)."""
    in_sec, found = False, []
    for line in read(TODO).split("\n"):
        if line.strip() == f"## {section}":
            in_sec = True
            continue
        if line.startswith("## ") and in_sec:
            break
        if in_sec and line.strip().startswith("- [ ]"):
            t = line.strip()[5:].strip()
            if t and not t.startswith("[Tortoise"):
                found.append(t)
    return found

def _is_chunk_task(task: str) -> bool:
    """True if this looks like a Tortoise build step (not free-form description)."""
    return task.startswith((
        "Create ", "Add ", "Wire ", "VERIFY", "Fix ", "Load ",
        "Implement ", "Handle ", "Final ", "Review ",
    ))

def next_task():
    """Return the active task: NOW first (interrupted/resume), then NEXT."""
    for t in _tasks_in_section("NOW"):
        if _is_chunk_task(t):
            return t
    for t in _tasks_in_section("NEXT"):
        return t
    return None

def task_to_now(task):
    """Move task to NOW section."""
    lines = read(TODO).split("\n")
    lines = [l for l in lines if l.strip() != f"- [ ] {task}"]
    out = []
    for line in lines:
        out.append(line)
        if line.strip() == "## NOW":
            out.append(f"- [ ] {task}")
    write(TODO, "\n".join(out))

def task_to_done(task):
    """Move task from NOW to DONE."""
    lines = read(TODO).split("\n")
    lines = [l for l in lines if l.strip() not in (f"- [ ] {task}", f"- [x] {task}")]
    out, in_done, added = [], False, False
    for line in lines:
        if line.strip() == "## DONE": in_done = True
        if in_done and not added:
            out.append(line)
            out.append(f"- [x] {task}")
            added = True
            continue
        out.append(line)
    write(TODO, "\n".join(out))

def add_tasks(tasks):
    """Add list of tasks under NEXT section."""
    if not tasks: return
    lines = read(TODO).split("\n")
    out, inserted = [], False
    for line in lines:
        out.append(line)
        if line.strip() == "## NEXT" and not inserted:
            for t in tasks:
                if t.strip(): out.append(f"- [ ] {t.strip()}")
            inserted = True
    write(TODO, "\n".join(out))

# ── Brain helpers ──────────────────────────────────────────────────────────────

def append_brain(update):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    write(BRAIN, read(BRAIN) + f"\n\n<!-- {ts} -->\n{update}")

def trim_brain_for_prompt(brain: str, max_updates: int = 3) -> str:
    """Keep stable header sections plus only the last N update blocks."""
    if not brain.strip():
        return brain
    markers = []
    for i, line in enumerate(brain.split("\n")):
        if re.match(r"^##\s+Update\s*\(", line) or re.match(r"^<!--\s+\d{4}-\d{2}-\d{2}", line):
            markers.append(i)
    if len(markers) <= max_updates:
        return brain
    cut = markers[-max_updates]
    header = "\n".join(brain.split("\n")[: markers[0]]).rstrip()
    tail = "\n".join(brain.split("\n")[cut:]).lstrip()
    note = f"\n\n[Earlier updates omitted — showing last {max_updates} only]\n"
    return f"{header}{note}\n{tail}"

def log_decision(task, text):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    write(DECISIONS, read(DECISIONS, "# Decisions\n") + f"\n## {ts} — {task}\n{text}\n")

def log_progress(n, task):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    write(PROGRESS, read(PROGRESS, "# Progress\n") + f"\n- [{ts}] Chunk {n:03d}: {task}")

def save_chunk(n, task, plan, decision):
    Path(CHUNKS_DIR).mkdir(exist_ok=True)
    safe = "".join(c for c in task[:40] if c.isalnum() or c in " -").strip().replace(" ","-")
    write(f"{CHUNKS_DIR}/{n:03d}-{safe}.md",
          f"# Chunk {n:03d}: {task}\n\n## Plan\n{plan}\n\n## Decision\n{decision}\n")

def chunk_count():
    return len(list(Path(CHUNKS_DIR).glob("*.md"))) if Path(CHUNKS_DIR).exists() else 0

def write_current(task, status, files=None):
    write(CURRENT, f"Status: {status}\nTask: {task}\nTime: {datetime.now()}\nFiles: {','.join(files or [])}\n")

def clear_current():
    p = Path(CURRENT)
    if p.exists(): p.unlink()

# ── File discovery ─────────────────────────────────────────────────────────────

def project_files(cfg):
    """List all (path, size) pairs not excluded."""
    excl = cfg.get("exclude", [])
    results = []
    for p in sorted(Path(".").rglob("*")):
        if not p.is_file(): continue
        ps = str(p)
        if any(e in ps for e in excl): continue
        try: results.append((ps, p.stat().st_size))
        except: pass
    return results

def relevant_files(task, all_files, cfg):
    """Score files by keyword overlap with task."""
    stop = {"a","an","the","to","in","on","for","of","and","or","add",
            "create","build","make","fix","update","write","implement"}
    kws  = [w.lower().strip("/:.-") for w in task.split()
            if len(w) > 2 and w.lower() not in stop]
    scored = []
    for fp, sz in all_files:
        score = sum(3 for k in kws if k in fp.lower())
        if sz < 5000: score += 1
        if any(fp.endswith(e) for e in [".py",".js",".ts",".go",".rb",".rs"]): score += 1
        if score > 0: scored.append((score, fp))
    scored.sort(reverse=True)
    return [fp for _, fp in scored[:cfg.get("max_files", 3)]]

def load_content(path, char_limit=3200):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
        if len(text) > char_limit:
            text = text[:char_limit] + f"\n\n[truncated — {len(text)} chars total]"
        return text
    except Exception as e:
        return f"[unreadable: {e}]"

# ── Backup ─────────────────────────────────────────────────────────────────────

def backup(files):
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = Path(BACKUP_DIR) / ts
    dst.mkdir(parents=True, exist_ok=True)
    for f in files:
        p = Path(f)
        if p.exists():
            shutil.copy2(p, dst / f.replace("/","__").replace("\\","__"))
    return str(dst)

def restore(backup_path):
    bp = Path(backup_path)
    if not bp.exists(): err(f"Backup not found: {backup_path}"); return
    for f in bp.iterdir():
        original = f.name.replace("__", os.sep)
        Path(original).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, original)
        ok(f"Restored {original}")

# ── Model call ─────────────────────────────────────────────────────────────────

def call_model(prompt, cfg):
    url     = cfg["endpoint"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        headers["Authorization"] = f"Bearer {cfg['api_key']}"

    body = json.dumps({
        "model":      cfg["model"],
        "max_tokens": cfg.get("max_tokens", 1500),
        "messages": [
            {"role": "system", "content":
             "You are a careful coding assistant working in small atomic chunks. "
             "Always follow the exact response format. Touch only listed files. "
             "Write PLAN before any code. Never skip a section."},
            {"role": "user", "content": prompt}
        ]
    }).encode()

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        info(f"Calling {cfg['model']} at {cfg['endpoint']} ...")
        with urllib.request.urlopen(req, timeout=300) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach model: {e}\n  Is Ollama running? Try: ollama serve")

# ── HTML validation ────────────────────────────────────────────────────────────

def _task_requires_js(task: str) -> bool:
    """True when this chunk should produce a <script> block (not skeleton/CSS-only)."""
    tlow = task.lower()
    if re.search(r"\bno\s+javascript\b", tlow) or "javascript yet" in tlow:
        return False
    if tlow.startswith("create index.html") and "skeleton" in tlow:
        return False
    if "add complete css" in tlow or ("<style>" in tlow and "script" not in tlow):
        return False
    return any(k in tlow for k in (
        "add <script", "<script>", "wire up", "verify:",
        "chart.js", "localstorage helpers", "interactive features",
    )) or tlow.startswith("verify")

def validate_html_content(content: str, task: str = "") -> list:
    """Return list of (level, message) where level is 'severe' or 'warn'."""
    issues = []
    low = content.lower()
    tlow = task.lower()

    if "<html" in low and "</html>" not in low:
        issues.append(("severe", "Missing </html> — file appears truncated"))
    if "<body" in low and "</body>" not in low:
        issues.append(("severe", "Missing </body>"))
    if "<form" in content and "</form>" not in content:
        issues.append(("severe", "Missing </form>"))

    for tag in ("html", "body", "head"):
        opens  = len(re.findall(rf"<{tag}(?:\s|>)", content, re.I))
        closes = len(re.findall(rf"</{tag}>", content, re.I))
        if opens > closes:
            issues.append(("severe", f"Unclosed <{tag}> tags ({opens} open, {closes} close)"))

    if re.search(r">[^<]*Project Brain[^<]*<", content, re.I):
        issues.append(("warn", "Visible UI says 'Project Brain' — use the App name from BRAIN.md"))

    if _task_requires_js(task) and "<script" not in low:
        issues.append(("severe", "Task requires JavaScript but no <script> block found"))

    if tlow.startswith("verify") or "wire up" in tlow:
        if "<form" in content and not re.search(r"addEventListener|onsubmit|\.submit", content):
            issues.append(("warn", "Form exists but no submit handler detected"))

    return issues

def _strip_js_noise(js: str) -> str:
    """Rough strip of strings/comments for brace counting."""
    s = re.sub(r"//[^\n]*", "", js)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.S)
    s = re.sub(r"`[^`\\]*(?:\\.[^`\\]*)*`", "``", s)
    s = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', s)
    s = re.sub(r"'[^'\\]*(?:\\.[^'\\]*)*'", "''", s)
    return s

def validate_js_content(html_content: str, task: str = "") -> list:
    """Lightweight JS wiring checks inside <script> blocks. Returns (level, message)."""
    issues = []
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html_content, re.I | re.S)
    if not scripts:
        return issues

    full_js = "\n".join(scripts)
    cleaned = _strip_js_noise(full_js)
    for open_c, close_c, label in (("{", "}", "braces"), ("[", "]", "brackets"), ("(", ")", "parens")):
        o, c = cleaned.count(open_c), cleaned.count(close_c)
        if o != c:
            issues.append(("severe", f"Mismatched {label} in <script> ({o} open, {c} close)"))

    html_ids = set(re.findall(r'\bid=["\']([^"\']+)["\']', html_content, re.I))
    for m in re.finditer(r'getElementById\(\s*["\']([^"\']+)["\']', full_js):
        if m.group(1) not in html_ids:
            issues.append(("severe", f"getElementById('{m.group(1)}') — no matching id in HTML"))
    for m in re.finditer(r'querySelector\(\s*["\']#([^"\']+)["\']', full_js):
        if m.group(1) not in html_ids:
            issues.append(("severe", f"querySelector('#{m.group(1)}') — no matching id in HTML"))
    for m in re.finditer(r'addEventListener\(\s*["\'](\w+)["\']', full_js):
        pass  # event type only — skip

    gets = set(re.findall(r'localStorage\.getItem\(\s*["\']([^"\']+)["\']', full_js))
    sets = set(re.findall(r'localStorage\.setItem\(\s*["\']([^"\']+)["\']', full_js))
    for key in gets:
        if key not in sets:
            issues.append(("severe", f"localStorage.getItem('{key}') with no setItem in this file"))

    if _task_requires_js(task):
        for pat in (r"addEventListener", r"\.onclick\s*=", r"onsubmit"):
            if re.search(pat, full_js, re.I):
                break
        else:
            if re.search(r"<button|<input[^>]+type=[\"']submit", html_content, re.I):
                issues.append(("warn", "Buttons/forms present but no event handlers in <script>"))

    return issues

GOLDEN_EXAMPLE_HTML = """\
EXAMPLE RESPONSE (format only — do not copy this app):

PLAN:
Add a minimal counter with localStorage persistence.

FILE: index.html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>Counter</title></head>
<body>
<h1>Counter</h1>
<button id="btn" type="button">Add</button>
<p id="count">0</p>
<script>
const KEY = "count";
let n = parseInt(localStorage.getItem(KEY) || "0", 10);
document.getElementById("btn").addEventListener("click", () => {
  n++; localStorage.setItem(KEY, String(n));
  document.getElementById("count").textContent = String(n);
});
document.getElementById("count").textContent = String(n);
</script>
</body>
</html>
ENDFILE

BRAIN_UPDATE:
Added counter UI and localStorage persistence.

TODO_DONE:
[task copied from CURRENT TASK]

TODO_ADD:
NONE

DECISION:
Single-file app with ids wired to script handlers.
"""

def _task_is_html(task: str, rel_files: list) -> bool:
    tlow = task.lower()
    if "index.html" in tlow or ".html" in tlow:
        return True
    return any(f.endswith(".html") for f in rel_files)

# ── Prompt builder ─────────────────────────────────────────────────────────────

def build_prompt(task, brain, all_files, rel_files, cfg):
    file_list = "\n".join(
        f"  {fp}  ({sz}b)" if sz < 1024 else f"  {fp}  ({sz//1024}kb)"
        for fp, sz in all_files[:60]
    )
    if len(all_files) > 60:
        file_list += f"\n  ... and {len(all_files)-60} more"

    per_file_chars = max(800, (cfg.get("context_limit",3000) - 800) * 4 // max(len(rel_files),1))
    file_blocks = ""
    for fp in rel_files:
        file_blocks += f"\n--- {fp} ---\n{load_content(fp, per_file_chars)}\n--- end ---\n"
    if not file_blocks.strip():
        file_blocks = "[No existing files loaded — likely creating new files]"

    constitution = read(CONSTITUTION).strip()
    const_block = ""
    if constitution:
        const_block = f"\nCONSTITUTION (follow on every chunk — non-negotiable):\n{constitution}\n"

    example_block = ""
    if _task_is_html(task, rel_files):
        example_block = f"\n{GOLDEN_EXAMPLE_HTML}\n"

    return f"""\
PROJECT BRAIN:
{brain}
{const_block}
CURRENT TASK:
{task}

ALL PROJECT FILES:
{file_list}

RELEVANT FILES FOR THIS TASK:
{file_blocks}

CRITICAL RULES:
- NEVER truncate a file. Every HTML file MUST end with </body></html>.
- Use the "App name" from BRAIN.md for <title> and <h1> — never "Project Brain".
- If index.html already exists, output the COMPLETE updated file (copy unchanged parts exactly).
- If the file would be very long, focus ONLY on what this task changes — but still close all tags.
- Include a <script> block with working JavaScript when the task involves interactivity or data.
- Every getElementById / #selector in JS must match an id that exists in the HTML.
- localStorage: every getItem key must have a setItem somewhere in the same file.
{example_block}
RESPOND IN EXACTLY THIS FORMAT — do not skip any section:

PLAN:
[3-5 lines explaining your approach before writing any code]

FILE: path/filename
[complete file content — must be valid and complete, not a partial snippet]
ENDFILE

[Repeat FILE...ENDFILE for each file. Omit section entirely if no files change.]

BRAIN_UPDATE:
[2-3 sentences on what changed in the project]

TODO_DONE:
{task}

TODO_ADD:
[new tasks you discovered, one per line. Write NONE if nothing new.]

DECISION:
[one paragraph on why you built it this way]
"""

# ── Response parser ────────────────────────────────────────────────────────────

class Parsed:
    def __init__(self):
        self.plan = ""; self.files = {}; self.brain_update = ""
        self.todo_add = []; self.decision = ""; self.raw = ""

def parse(text):
    p = Parsed(); p.raw = text

    def section(start, *stops):
        i = text.find(start)
        if i == -1: return ""
        i += len(start)
        end = len(text)
        for s in stops:
            j = text.find(s, i)
            if j != -1 and j < end: end = j
        return text[i:end].strip()

    sections = ["PLAN:","FILE:","BRAIN_UPDATE:","TODO_DONE:","TODO_ADD:","DECISION:"]
    p.plan         = section("PLAN:",         *sections[1:])
    p.brain_update = section("BRAIN_UPDATE:", "TODO_DONE:","TODO_ADD:","DECISION:")
    p.decision     = section("DECISION:")

    raw_add = section("TODO_ADD:", "DECISION:")
    if raw_add and raw_add.strip().upper() != "NONE":
        for line in raw_add.split("\n"):
            t = line.strip().lstrip("- ").strip()
            if t and t.upper() != "NONE": p.todo_add.append(t)

    # Parse FILE blocks
    rest = text
    while True:
        fi = rest.find("FILE:")
        if fi == -1: break
        le = rest.find("\n", fi)
        if le == -1: break
        fname = rest[fi+5:le].strip()
        cs = le + 1
        ei = rest.find("ENDFILE", cs)
        if ei == -1:
            # graceful: grab until next FILE: or BRAIN_UPDATE:
            nxt = min((rest.find(m, cs) for m in ["FILE:","BRAIN_UPDATE:"]
                       if rest.find(m, cs) != -1), default=len(rest))
            content = rest[cs:nxt].strip()
            rest = rest[nxt:]
        else:
            content = rest[cs:ei].strip()
            rest = rest[ei+7:]
        # Strip markdown fences if model added them
        if content.startswith("```"):
            lines = content.split("\n")[1:]
            if lines and lines[-1].strip() == "```": lines = lines[:-1]
            content = "\n".join(lines)
        if fname: p.files[fname] = content

    return p

# ── Diff display ───────────────────────────────────────────────────────────────

def show_diff(path, new):
    old = Path(path).read_text(encoding="utf-8") if Path(path).exists() else ""
    if old == new: print(dim(f"    {path}: unchanged")); return False
    diff = list(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile=f"a/{path}", tofile=f"b/{path}", n=2))
    if not diff: return False
    print(f"\n  {bold(path)}")
    for line in diff[:50]:
        line = line.rstrip("\n")
        if   line.startswith("+") and not line.startswith("+++"): print(green(f"    {line}"))
        elif line.startswith("-") and not line.startswith("---"): print(red(f"    {line}"))
        elif line.startswith("@@"): print(cyan(f"    {line}"))
        else: print(dim(f"    {line}"))
    if len(diff) > 50: print(dim(f"    ... {len(diff)-50} more lines"))
    return True

# ── Guard ──────────────────────────────────────────────────────────────────────

def need_init():
    if not Path(T).exists():
        err("Not a tortoise project. Run: tortoise init")
        sys.exit(1)

# ══ COMMANDS ═══════════════════════════════════════════════════════════════════

def cmd_init(args):
    head("Tortoise Init")
    if Path(T).exists() and not confirm("Already initialized. Reinit?"):
        return
    for d in [T, CHUNKS_DIR, BACKUP_DIR]: Path(d).mkdir(parents=True, exist_ok=True)
    if not Path(BRAIN).exists():    write(BRAIN,     BRAIN_INIT);    ok(f"Created {BRAIN}")
    if not Path(TODO).exists():     write(TODO,      TODO_INIT);     ok(f"Created {TODO}")
    if not Path(PROGRESS).exists(): write(PROGRESS,  "# Progress\n"); ok(f"Created {PROGRESS}")
    if not Path(DECISIONS).exists():write(DECISIONS, "# Decisions\n");ok(f"Created {DECISIONS}")
    if not Path(CONFIG).exists():   save_cfg(DEFAULT_CONFIG);         ok(f"Created {CONFIG}")

    # .gitignore — never commit secrets, backups, or interrupt state
    gi = Path(".gitignore")
    entry = (
        "\n# Tortoise (local only — may contain API keys in config.json)\n"
        ".tortoise/config.json\n"
        ".tortoise/backups/\n"
        ".tortoise/CURRENT.md\n"
    )
    if gi.exists():
        text = gi.read_text()
        if ".tortoise/config.json" not in text:
            gi.open("a").write(entry)
    else:
        write(".gitignore", entry.lstrip("\n"))

    print(f"\n  {bold('Next steps:')}")
    print(f"  1. Edit {BRAIN} — describe your project")
    print(f"  2. Run: tortoise plan \"your goal\"   (model breaks it into tasks)")
    print(f"     OR: tortoise add \"first task\"")
    print(f"  3. Run: tortoise run\n")


def cmd_config(args):
    need_init()
    cfg = load_cfg()
    if args.endpoint:     cfg["endpoint"]      = args.endpoint;      ok(f"endpoint → {args.endpoint}")
    if args.model:        cfg["model"]         = args.model;         ok(f"model → {args.model}")
    if args.api_key:      cfg["api_key"]       = args.api_key;       ok("api_key saved")
    if args.max_tokens:   cfg["max_tokens"]    = int(args.max_tokens)
    if args.yes:          cfg["confirm_writes"]= False;              ok("auto-confirm enabled")
    if args.confirm:      cfg["confirm_writes"]= True;               ok("confirmation enabled")
    save_cfg(cfg)
    if not any([args.endpoint, args.model, args.api_key, args.max_tokens, args.yes, args.confirm]):
        head("Current Config")
        for k, v in cfg.items():
            print(f"  {k}: {'*'*8 if k=='api_key' else v}")


def cmd_add(args):
    need_init()
    task = " ".join(args.task).strip()
    if not task: err("Provide a task description"); return
    add_tasks([task])
    ok(f"Added: {task}")
    info("Run 'tortoise run' to execute")


def cmd_status(args):
    need_init()
    cfg = load_cfg()
    head("Tortoise Status")
    print(f"  {dim('model:')} {cfg['model']}  {dim('endpoint:')} {cfg['endpoint']}")
    print(f"  {dim('chunks completed:')} {chunk_count()}")
    if Path(STOP_FILE).exists(): warn("STOP file present — remove .tortoise/STOP to continue")
    if Path(CURRENT).exists(): warn("Interrupted chunk detected — run: tortoise resume")
    now = [t for t in _tasks_in_section("NOW") if _is_chunk_task(t)]
    task = next_task()
    if now and now[0] != task:
        print(f"\n  {bold('Active task (NOW):')} {now[0]}")
    if task:
        print(f"\n  {bold('Next up:')} {task}")
    else:
        print(f"\n  {yellow('No tasks queued')} — run: tortoise add \"task\"")
    print()


def cmd_run(args):
    need_init()
    if Path(STOP_FILE).exists(): warn("STOP file found. Remove .tortoise/STOP to continue."); return
    cfg  = load_cfg()
    task = next_task()
    if not task: warn("No tasks in queue."); info("Add one: tortoise add \"task\""); return

    head("Running Chunk")
    print(f"  {bold('Task:')} {task}\n")

    all_f = project_files(cfg)
    rel_f = relevant_files(task, all_f, cfg)

    if args.dry:
        info(f"Relevant files: {rel_f or ['(none — new files)']}")
        info("Dry run — nothing written"); return

    if rel_f: info(f"Relevant files: {', '.join(rel_f)}")
    else:     info("No existing files matched — likely new files")

    brain  = trim_brain_for_prompt(read(BRAIN))
    prompt = build_prompt(task, brain, all_f, rel_f, cfg)

    write_current(task, "CALLING_MODEL", rel_f)
    task_to_now(task)

    try:
        response = call_model(prompt, cfg)
    except RuntimeError as e:
        err(str(e)); return

    parsed = parse(response)
    if not parsed.files:
        warn("No files parsed — retrying with stricter format prompt")
        retry = f"""Your last response was missing parseable FILE blocks. Reply ONLY in this exact format.

CURRENT TASK: {task}

PLAN:
[2-3 lines]

FILE: index.html
[complete file — all tags closed, working script if needed]
ENDFILE

BRAIN_UPDATE:
[one sentence]

TODO_DONE:
{task}

TODO_ADD:
NONE

DECISION:
[one sentence]
"""
        try:
            response = call_model(retry, cfg)
            parsed = parse(response)
        except RuntimeError as e:
            err(str(e)); return

    # Show plan
    if parsed.plan:
        print(f"\n  {bold('Plan:')}")
        for line in parsed.plan.strip().split("\n"):
            print(f"  {dim(line)}")

    # Show diffs
    if parsed.files:
        print(f"\n  {bold(f'Changes ({len(parsed.files)} file(s)):')} ")
        for fp, content in parsed.files.items():
            show_diff(fp, content)

        if cfg.get("confirm_writes", True) and not args.yes:
            print()
            if not confirm(f"Write {len(parsed.files)} file(s)?"):
                warn("Aborted — task stays in queue"); return

        write_current(task, "WRITING", list(parsed.files.keys()))
        if cfg.get("backup", True):
            bp = backup(list(parsed.files.keys()))
            info(f"Backup → {bp}")

        validation_errors = []
        for fp, content in parsed.files.items():
            if fp.endswith(".html"):
                for level, msg in validate_html_content(content, task):
                    (err if level == "severe" else warn)(f"HTML check ({fp}): {msg}")
                    if level == "severe":
                        validation_errors.append(f"{fp}: {msg}")
                for level, msg in validate_js_content(content, task):
                    (err if level == "severe" else warn)(f"JS check ({fp}): {msg}")
                    if level == "severe":
                        validation_errors.append(f"{fp}: {msg}")

        if validation_errors:
            err("Write blocked — fix validation issues and run again (task stays in queue)")
            clear_current()
            return

        for fp, content in parsed.files.items():
            write(fp, content)
            ok(f"Written: {fp}")
    else:
        info("No file changes in this chunk")

    # Update brain
    write_current(task, "UPDATING_BRAIN")
    if parsed.brain_update: append_brain(parsed.brain_update)
    if parsed.todo_add:
        add_tasks(parsed.todo_add)
        info(f"Added {len(parsed.todo_add)} new task(s) to TODO")

    n = chunk_count() + 1
    task_to_done(task)
    log_decision(task, parsed.decision or "(none)")
    log_progress(n, task)
    save_chunk(n, task, parsed.plan, parsed.decision)
    clear_current()

    print()
    ok(f"Chunk {n:03d} complete: {task}")
    nxt = next_task()
    if nxt: print(f"  {dim('Next:')} {nxt}  —  run: tortoise run")
    else:   print(f"  {green('Queue empty.')} Add more: tortoise add \"task\"")
    print()


def cmd_resume(args):
    need_init()
    if not Path(CURRENT).exists(): info("No interrupted chunk. Run: tortoise run"); return
    head("Resuming")
    current = read(CURRENT)
    status  = next((l.split(":",1)[1].strip() for l in current.split("\n") if l.startswith("Status:")), "")
    if "WRITING" in status:
        warn("Interrupted during write. Rolling back first.")
        cmd_rollback(argparse.Namespace())
    clear_current()
    cmd_run(args)


def cmd_rollback(args):
    need_init()
    backups = sorted(Path(BACKUP_DIR).iterdir()) if Path(BACKUP_DIR).exists() else []
    if not backups: warn("No backups found"); return
    last = backups[-1]
    files = list(last.iterdir())
    if not files: warn("Backup is empty"); return
    head(f"Rollback — {last.name}")
    for f in files: print(f"  {f.name}")
    if not confirm("Restore these files?"): return
    restore(str(last))
    ok("Rollback complete")


def cmd_plan(args):
    need_init()
    cfg  = load_cfg()
    goal = " ".join(args.goal).strip()
    if not goal: err("Provide a goal to plan"); return

    head(f"Planning: {goal}")
    brain  = read(BRAIN)
    prompt = f"""\
PROJECT BRAIN:
{brain}

GOAL: {goal}

Break this into a list of small atomic coding tasks.
Each task should touch 1-3 files. Order by dependency.
Be specific: not "build auth" but "create src/auth.py with login() function".

RESPOND ONLY WITH:
TASKS:
- task one
- task two
- etc
"""
    try:
        response = call_model(prompt, cfg)
    except RuntimeError as e:
        err(str(e)); return

    tasks = []
    in_tasks = False
    for line in response.split("\n"):
        if "TASKS:" in line: in_tasks = True; continue
        if in_tasks:
            t = line.strip().lstrip("0123456789.-) ").strip()
            if t and len(t) > 4: tasks.append(t)

    if not tasks: warn("Could not parse tasks. Raw response:"); print(response); return

    print(f"\n  {bold(f'{len(tasks)} tasks generated:')}")
    for i, t in enumerate(tasks, 1): print(f"  {dim(str(i)+'.')} {t}")

    print()
    if confirm(f"Add all {len(tasks)} tasks to TODO?"):
        add_tasks(tasks)
        ok(f"Added {len(tasks)} tasks")
        info("Run: tortoise run")


def cmd_brain(args):
    need_init(); print(read(BRAIN))

def cmd_todo(args):
    need_init(); print(read(TODO))

def cmd_log(args):
    need_init()
    chunks = sorted(Path(CHUNKS_DIR).glob("*.md")) if Path(CHUNKS_DIR).exists() else []
    if not chunks: info("No completed chunks yet"); return
    head(f"Completed Chunks ({len(chunks)})")
    for c in chunks: print(f"  {c.stem}")
    print()

# ── CLI entry point ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="tortoise",
        description="Chunk-based coding harness for slow, small, local AI models.")
    parser.add_argument("--version", action="version", version=f"tortoise {VERSION}")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init", help="Initialize tortoise in current directory")

    p_cfg = sub.add_parser("config", help="Show or update configuration")
    p_cfg.add_argument("--endpoint",   help="Model API endpoint URL")
    p_cfg.add_argument("--model",      help="Model name")
    p_cfg.add_argument("--api-key",    dest="api_key", help="API key (if required)")
    p_cfg.add_argument("--max-tokens", dest="max_tokens", help="Max tokens per response")
    p_cfg.add_argument("--yes",        action="store_true", help="Disable write confirmation")
    p_cfg.add_argument("--confirm",    action="store_true", help="Enable write confirmation")

    p_add = sub.add_parser("add", help="Add a task to TODO")
    p_add.add_argument("task", nargs="+")

    sub.add_parser("status", help="Show project status")

    p_run = sub.add_parser("run", help="Execute next chunk")
    p_run.add_argument("--yes", action="store_true", help="Skip confirmation")
    p_run.add_argument("--dry", action="store_true", help="Show plan without writing")

    p_res = sub.add_parser("resume", help="Continue interrupted chunk")
    p_res.add_argument("--yes", action="store_true")

    sub.add_parser("rollback", help="Restore files from last backup")

    p_plan = sub.add_parser("plan", help="Break a goal into atomic tasks")
    p_plan.add_argument("goal", nargs="+")

    sub.add_parser("brain",   help="Print BRAIN.md")
    sub.add_parser("todo",    help="Print TODO.md")
    sub.add_parser("log",     help="List completed chunks")

    args = parser.parse_args()

    dispatch = {
        "init": cmd_init, "config": cmd_config, "add": cmd_add,
        "status": cmd_status, "run": cmd_run, "resume": cmd_resume,
        "rollback": cmd_rollback, "plan": cmd_plan,
        "brain": cmd_brain, "todo": cmd_todo, "log": cmd_log,
    }

    if args.cmd in dispatch:
        dispatch[args.cmd](args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
