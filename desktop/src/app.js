// The page: a form for voices.yaml, and buttons that run the vk steps. All the work is in the
// Python package; Rust (src-tauri/src/main.rs) starts it and passes its output here.
const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const $ = (id) => document.getElementById(id);
const PLACEHOLDER_USERNAME = "your-kaggle-username";
const MAX_LOG_LINES = 2000;
const STEP_BUTTONS = ["save", "upload", "record", "resume", "restart", "download", "listen", "export", "open-folder",
  "record-fixes", "download-takes", "listen-takes", "use-takes"];
const CONFIRM_SECONDS = 8;
const POLL_SECONDS = 60; // how often the window asks Kaggle while a notebook is queued or running
const STILL_GOING = ["QUEUED", "RUNNING", "NONE"]; // NONE: just pushed, not listed yet
const FAILED = ["ERROR", "CANCEL_REQUESTED", "CANCEL_ACKNOWLEDGED"];
const CHIP = { QUEUED: "waiting", NONE: "waiting", RUNNING: "running", COMPLETE: "done" };
const LABEL = { NONE: "starting" };

let voices = [];
let own = null; // a speaker's own lines, kept as the file has them
let busy = false;
let restartArmed = null; // the timer while "Start over" waits for its second click
let pollTimer = null;

// ---- talking to the app ----

async function api(args, input) {
  const answer = await invoke("api", { args, input: input ?? null });
  if (!answer.ok) throw new Error(answer.error);
  return answer;
}

async function runStep(args) {
  setBusy(true);
  log(`$ vk ${args.join(" ")}`);
  try {
    const ok = await invoke("run_vk", { folder: folder(), args });
    log(ok ? "done" : "failed: see the lines above");
    return ok;
  } catch (error) {
    log(String(error) === "stopped" ? "stopped (what already started on Kaggle keeps running)" : `error: ${error}`);
    return false;
  } finally {
    setBusy(false);
  }
}

// ---- the form ----

function folder() {
  return $("folder").value.trim();
}

function results(...parts) {
  return [folder(), ...parts].join("/");
}

async function openFolder(path) {
  $("folder").value = path;
  const answer = await api(["open", path]);
  voices = answer.builtin_voices;
  $("folder").value = answer.folder;
  showProblem(answer.problem);
  const project = answer.project;
  own = project ? project.own : null;
  $("project").value = project ? project.project : "";
  $("username").value = project ? project.username : "";
  $("lines").value = project ? project.sentences.join("\n") : "";
  $("speakers").replaceChildren();
  (project ? project.speakers : []).forEach(addSpeaker);
  if (!project) addSpeaker({ id: "narrator", mode: "builtin", value: voices[0], transcript: "" });
  const ownCount = own ? Object.values(own).reduce((n, lines) => n + lines.length, 0) : 0;
  $("own-note").textContent = ownCount
    ? `Every speaker says these lines. ${ownCount} line(s) said by one speaker only are kept as they are.`
    : "Every speaker says these lines.";
  showRun(answer.run);
  showFixStep(project); // fix.js
}

function showRun(run) {
  const started = Boolean(run && (run.pushed.length || run.check_pushed));
  $("resume").hidden = !(run && run.unfinished);
  $("record").hidden = started; // a run exists: starting again is "Start over", with a confirm
  $("restart").hidden = !started;
  disarmRestart();
  $("notebooks").hidden = true;
  $("download").classList.remove("primary");
  pollSoon(started ? 0 : null);
  if (run && run.unfinished) {
    setStatus(`A recording was started (${run.pushed.join(", ")}). Resume to follow it and start the check.`);
  } else if (run && run.check_pushed) {
    setStatus("The check was started on Kaggle. Download the results when it is COMPLETE.");
  } else {
    setStatus("Nothing running.");
  }
}

// ---- Kaggle status of the run's notebooks ----

function pollSoon(seconds) {
  clearTimeout(pollTimer);
  pollTimer = seconds === null ? null : setTimeout(pollStatus, seconds * 1000);
}

async function pollStatus() {
  const asked = folder();
  if (busy) return pollSoon(POLL_SECONDS); // a running vk step prints its own status lines
  let notebooks;
  try {
    notebooks = (await api(["status", asked])).notebooks;
  } catch (error) {
    $("notebooks").hidden = false;
    $("notebooks").textContent = `Could not ask Kaggle (${error.message}). Trying again in a minute.`;
    return pollSoon(POLL_SECONDS);
  }
  if (asked !== folder() || busy) return pollSoon(POLL_SECONDS); // another project, or a step started
  showNotebooks(notebooks);
  const going = Object.values(notebooks).some((status) => STILL_GOING.includes(status));
  pollSoon(going ? POLL_SECONDS : null);
}

function showNotebooks(notebooks) {
  const fixLine = fixStatus(notebooks); // fix.js; may change notebooks.fix
  const box = $("notebooks");
  box.replaceChildren();
  for (const [name, status] of Object.entries(notebooks)) {
    const chip = document.createElement("span");
    chip.className = `chip ${FAILED.includes(status) ? "failed" : CHIP[status] || "waiting"}`;
    chip.textContent = `${name} ${LABEL[status] || status.toLowerCase().replaceAll("_", " ")}`;
    box.append(chip);
  }
  const time = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const note = document.createElement("span");
  note.className = "muted";
  note.textContent = `Kaggle, ${time}`;
  box.append(note);
  box.hidden = Object.keys(notebooks).length === 0;
  const check = notebooks.check;
  $("download").classList.toggle("primary", check === "COMPLETE");
  if (fixLine) {
    setStatus(fixLine);
  } else if (check) {
    setStatus(CHECK_STATUS[FAILED.includes(check) ? "FAILED" : check] || CHECK_STATUS.QUEUED);
  } else if (Object.values(notebooks).some((status) => FAILED.includes(status))) {
    setStatus("A recording notebook failed or was cancelled on Kaggle (its log is on kaggle.com). " +
      "Start over to record again.");
  }
}

const CHECK_STATUS = {
  NONE: "The check was just started on Kaggle.",
  QUEUED: "The check is waiting for a free Kaggle GPU. This updates every minute.",
  RUNNING: "The check is running on Kaggle: it listens to every clip and records the bad ones again. " +
    "This updates every minute.",
  COMPLETE: "The check is COMPLETE. Download the results.",
  FAILED: "The check failed or was cancelled on Kaggle. Open it on kaggle.com to see the log.",
};

function showProblem(text) {
  $("project-problem").hidden = !text;
  $("project-problem").textContent = text || "";
}

function addSpeaker(speaker) {
  const row = $("speaker-row").content.firstElementChild.cloneNode(true);
  row.querySelector(".speaker-id").value = speaker.id;
  const mode = row.querySelector(".speaker-mode");
  mode.value = speaker.mode;
  mode.addEventListener("change", () => fillValue(row, { mode: mode.value, value: "", transcript: "" }));
  row.querySelector(".remove").addEventListener("click", () => row.remove());
  fillValue(row, speaker);
  $("speakers").append(row);
}

function fillValue(row, speaker) {
  const box = row.querySelector(".speaker-value");
  box.replaceChildren();
  if (speaker.mode === "builtin") {
    const select = document.createElement("select");
    for (const name of voices) select.append(new Option(name, name));
    select.value = voices.includes(speaker.value) ? speaker.value : voices[0];
    box.append(select);
  } else if (speaker.mode === "clip") {
    const line = document.createElement("span");
    line.className = "row";
    const path = input(speaker.value, "clips/me.ogg");
    path.classList.add("clip-path");
    const choose = document.createElement("button");
    choose.type = "button";
    choose.textContent = "Choose…";
    choose.addEventListener("click", async () => {
      const picked = await invoke("pick", { kind: "clip" });
      if (picked) path.value = picked;
    });
    line.append(path, choose);
    const words = input(speaker.transcript, "The exact words said in the clip");
    words.classList.add("clip-words");
    words.dir = "auto";
    box.append(line, words);
  } else {
    box.append(input(speaker.value, "e.g. a calm male voice, slow pace"));
  }
}

function input(value, placeholder) {
  const element = document.createElement("input");
  element.value = value || "";
  element.placeholder = placeholder;
  element.spellcheck = false;
  return element;
}

function draft() {
  const speakers = [...document.querySelectorAll("#speakers .speaker")].map((row) => {
    const mode = row.querySelector(".speaker-mode").value;
    const id = row.querySelector(".speaker-id").value.trim();
    if (mode === "clip") {
      return { id, mode, value: row.querySelector(".clip-path").value, transcript: row.querySelector(".clip-words").value };
    }
    const value = row.querySelector(".speaker-value select, .speaker-value input").value;
    return { id, mode, value, transcript: "" };
  });
  const sentences = $("lines").value.split("\n").map((line) => line.trim()).filter(Boolean);
  const project = { folder: folder(), project: $("project").value.trim(), username: $("username").value.trim(), speakers, sentences };
  if (own) project.own = own;
  return project;
}

async function save() {
  const project = draft();
  if (!project.username || project.username === PLACEHOLDER_USERNAME) {
    throw new Error("enter your Kaggle username (the name in kaggle.com/<name>)");
  }
  await api(["save"], JSON.stringify(project));
  log(`saved ${folder()}/voices.yaml`);
}

// ---- token ----

async function checkToken() {
  const answer = await api(["token"]);
  const status = $("token-status");
  if (!answer.kaggle_cli) {
    status.textContent = "The Kaggle command is missing from the app's Python. Run desktop/install.sh again.";
    status.className = "error";
  } else if (answer.token) {
    status.textContent = "Kaggle token found.";
    status.className = "ok";
  } else {
    status.textContent = "No Kaggle token yet. Create one at kaggle.com → Settings → API, then paste it below.";
    status.className = "error";
  }
}

async function saveToken(args, input) {
  await api(["token", ...args], input);
  $("token").value = "";
  log("Kaggle token saved in ~/.kaggle");
  await checkToken();
}

// ---- running steps ----

function setBusy(value) {
  busy = value;
  for (const id of STEP_BUTTONS) $(id).disabled = value;
  $("stop").hidden = !value;
}

function setStatus(text) {
  $("status").textContent = text;
}

function log(text) {
  const shown = text.split("\r").pop(); // progress bars rewrite their line with \r
  const pane = $("log");
  pane.append(shown + "\n");
  while (pane.childNodes.length > MAX_LOG_LINES) pane.firstChild.remove();
  pane.scrollTop = pane.scrollHeight;
  if (/^\d\d:\d\d\s+\S+=\S+/.test(shown) || /GPU slots are busy/.test(shown)) setStatus(shown);
  if (/^check (started|was already started)/.test(shown)) setStatus("The check was started on Kaggle. Download the results when it is COMPLETE.");
}

function action(id, run) {
  $(id).addEventListener("click", async () => {
    if (busy && id !== "stop") return;
    try {
      await run();
    } catch (error) {
      log(`error: ${error.message || error}`);
    }
  });
}

action("open-folder", () => openFolder(folder()));
action("choose-folder", async () => {
  const picked = await invoke("pick", { kind: "folder" });
  if (picked) await openFolder(picked);
});
action("save-token", async () => {
  if (!$("token").value.trim()) throw new Error("paste the token first");
  await saveToken(["--set"], $("token").value);
});
action("choose-token", async () => {
  const picked = await invoke("pick", { kind: "file" });
  if (picked) await saveToken(["--copy", picked]);
});
action("add-speaker", async () => addSpeaker({ id: "", mode: "builtin", value: voices[0], transcript: "" }));
action("save", save);
action("upload", async () => {
  await save();
  await runStep(["dataset", "--upload"]);
});
async function startRecording() {
  await save();
  // The notebooks stop on Kaggle if the dataset there is older than the saved project.
  const { dataset_current: current } = await api(["open", folder()]);
  if (current || (await runStep(["dataset", "--upload"]))) {
    if (await runStep(["record"])) await runStep(["watch"]);
  }
  await openFolder(folder());
}

function disarmRestart() {
  clearTimeout(restartArmed);
  restartArmed = null;
  $("restart").textContent = "Start over";
  $("restart").classList.remove("danger");
}

action("record", startRecording);
// Start over rebuilds every notebook and records every line again, so it takes a second click.
action("restart", async () => {
  if (!restartArmed) {
    restartArmed = setTimeout(disarmRestart, CONFIRM_SECONDS * 1000);
    $("restart").textContent = "Click again to start over";
    $("restart").classList.add("danger");
    setStatus("Start over records every line again from the beginning. Notebooks still running on " +
      "Kaggle keep running and use your GPU hours: stop them on kaggle.com first.");
    return;
  }
  disarmRestart();
  await startRecording();
});
action("resume", async () => {
  await runStep(["watch", "--resume"]);
  await openFolder(folder());
});
action("stop", () => invoke("stop_vk"));
action("download", () => runStep(["fetch", "check"]));
action("listen", async () => {
  if (await runStep(["listen", results("build", "out", "check", "voices_checked.zip"), "--all"])) {
    await invoke("open_path", { path: results("build", "listen", "voices_checked", "index.html") });
  }
});
action("export", async () => {
  const out = await invoke("pick", { kind: "folder" });
  if (!out) return;
  if (await runStep(["export", results("build", "out", "check", "voices_checked.zip"), "--out", out])) {
    await invoke("open_path", { path: out });
  }
});

listen("vk-log", (event) => log(event.payload));

// ---- tabs ----

const TABS = [...document.querySelectorAll('[role="tab"]')];

function showTab(name) {
  for (const tab of TABS) {
    const selected = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    $(tab.getAttribute("aria-controls")).hidden = !selected;
  }
}

for (const tab of TABS) {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
  tab.addEventListener("keydown", (event) => { // arrow keys move between tabs
    const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
    if (!step) return;
    const next = TABS[(TABS.indexOf(tab) + step + TABS.length) % TABS.length];
    showTab(next.dataset.tab);
    next.focus();
  });
}

// Start once every script on the page (fix.js too) has run.
window.addEventListener("DOMContentLoaded", async () => {
  showTab("setup");
  try {
    await checkToken();
    await openFolder(await invoke("start_folder"));
    if (!$("restart").hidden) showTab("record"); // a recording was started: show where it stands
  } catch (error) {
    log(`error: ${error.message || error}`);
  }
});
