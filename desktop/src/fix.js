// Step 7, fixing lines that sound wrong: the same as `vk fix`, `vk push fix`, `vk fetch fix`,
// `vk listen fix.zip` and `vk use-take`. Uses the helpers in app.js (api, runStep, action, ...).
const FIX_TAKES = [1, 2, 3, 4, 5];
const KEEP = ""; // the radio value for "keep the clip I have now"

let fixProject = null; // the project as saved: line numbers must match the recording
let fixStarting = false; // pushed, but Kaggle may still show the previous run's COMPLETE
let fixWasGoing = false;

function showFixStep(project) {
  fixProject = project;
  $("fixes").replaceChildren();
  $("fix-step").hidden = !project;
  $("fix-empty").hidden = Boolean(project);
  $("takes").replaceChildren();
  $("use-takes").hidden = true;
  if (project) loadTakes(true);
}

function speakerLines(speaker) {
  return [...fixProject.sentences, ...((fixProject.own || {})[speaker] || [])];
}

function addFixRow() {
  if (!fixProject || !fixProject.speakers.length) throw new Error("save a project with speakers first");
  const row = $("fix-row").content.firstElementChild.cloneNode(true);
  const speaker = row.querySelector(".fix-speaker");
  const line = row.querySelector(".fix-line");
  const spellings = row.querySelector(".fix-spellings");
  for (const s of fixProject.speakers) speaker.append(new Option(s.id, s.id));
  const fillLines = () => {
    line.replaceChildren();
    speakerLines(speaker.value).forEach((text, n) => line.append(new Option(`${n} · ${text}`, n)));
    spellings.value = speakerLines(speaker.value)[0] || "";
  };
  speaker.addEventListener("change", fillLines);
  line.addEventListener("change", () => { spellings.value = speakerLines(speaker.value)[Number(line.value)]; });
  row.querySelector(".remove").addEventListener("click", () => row.remove());
  fillLines();
  $("fixes").append(row);
}

function fixLines() {
  const rows = [...document.querySelectorAll("#fixes .fix")].map((row) => ({
    speaker: row.querySelector(".fix-speaker").value,
    line: Number(row.querySelector(".fix-line").value),
    spellings: row.querySelector(".fix-spellings").value.split("\n").map((s) => s.trim()).filter(Boolean),
  }));
  if (!rows.length) throw new Error("add a line to fix first");
  const empty = rows.find((row) => !row.spellings.length);
  if (empty) throw new Error(`write at least one spelling for ${empty.speaker}, line ${empty.line}`);
  return rows;
}

async function recordFixes() {
  const answer = await api(["fix-save", folder()], JSON.stringify({ takes: Number($("fix-takes").value), lines: fixLines() }));
  log(`${answer.clips} clip(s) to record`);
  // Like the recording, the fix notebook stops on Kaggle if the dataset there is older.
  const { dataset_current: current } = await api(["open", folder()]);
  if (!current && !(await runStep(["dataset", "--upload"]))) return;
  if (!(await runStep(["fix", answer.path]))) return;
  if (!(await runStep(["push", "fix"]))) return;
  fixStarting = true;
  setStatus("The fix notebook was started on Kaggle. This updates every minute.");
  pollSoon(5);
}

// Called by showNotebooks in app.js before it draws the chips. Returns a status line, or null.
function fixStatus(notebooks) {
  const status = notebooks.fix;
  if (!status) return null;
  if (fixStarting && ["QUEUED", "RUNNING"].includes(status)) fixStarting = false;
  if (fixStarting && status === "COMPLETE") notebooks.fix = "NONE"; // the old run, until the new starts
  const now = notebooks.fix;
  const going = STILL_GOING.includes(now);
  const justFinished = fixWasGoing && now === "COMPLETE";
  if (going) fixWasGoing = true;
  $("download-takes").classList.toggle("primary", justFinished);
  if (going) return "The fix notebook is recording your spellings on Kaggle. This updates every minute.";
  if (justFinished) return "The fix takes are ready: Download takes, listen, then pick the best.";
  if (FAILED.includes(now)) return "The fix notebook failed or was cancelled on Kaggle. Open it on kaggle.com to see the log.";
  return null;
}

async function loadTakes(quiet) {
  let clips;
  try {
    clips = (await api(["takes", folder()])).clips;
  } catch (error) {
    if (!quiet) log(`error: ${error.message}`);
    return;
  }
  const box = $("takes");
  box.replaceChildren();
  for (const clip of clips) {
    const group = document.createElement("fieldset");
    group.className = "take-group";
    const legend = document.createElement("legend");
    legend.textContent = `${clip.speaker} · line ${clip.line}`;
    const sentence = document.createElement("div");
    sentence.className = "muted";
    sentence.dir = "auto";
    sentence.textContent = clip.sentence;
    group.append(legend, sentence, radio(clip, KEEP, "Keep the clip I have now", true));
    for (const take of clip.takes) {
      group.append(radio(clip, take.name, `${take.variant}${take.take} · ${take.text}`, false));
    }
    box.append(group);
  }
  $("use-takes").hidden = clips.length === 0;
}

function radio(clip, value, text, checked) {
  const label = document.createElement("label");
  label.className = "take";
  const input = document.createElement("input");
  input.type = "radio";
  input.name = `take-${clip.speaker}-${clip.line}`;
  input.value = value;
  input.checked = checked;
  const span = document.createElement("span");
  span.dir = "auto";
  span.textContent = text;
  label.append(input, span);
  return label;
}

async function useTakes() {
  const picked = [...document.querySelectorAll("#takes input[type=radio]:checked")]
    .map((input) => input.value).filter((value) => value !== KEEP);
  if (!picked.length) throw new Error("pick a take for at least one line (or keep them all)");
  const answer = await api(["use-takes", folder(), ...picked]);
  log(`used ${picked.join(", ")} in voices_checked.zip (the original is kept as ${answer.backup})`);
  log(answer.pronunciation
    ? `added the spelling(s) to ${answer.pronunciation}, so later recordings say them the same way`
    : "this project has no pronunciation file: add these to one to keep them for later recordings: " +
      JSON.stringify(answer.lines));
  setStatus("Takes used. Listen again, then Export.");
  await loadTakes(true);
}

for (const n of FIX_TAKES) $("fix-takes").append(new Option(n, n, false, n === 2));
action("add-fix", async () => addFixRow());
action("record-fixes", recordFixes);
action("download-takes", async () => {
  if (await runStep(["fetch", "fix"])) await loadTakes(false);
});
action("listen-takes", async () => {
  const page = results("build", "listen", "fix", "index.html");
  const args = ["listen", results("build", "out", "fix", "fix.zip"), "--compare",
    results("build", "out", "check", "voices_checked.zip"), "--out", results("build", "listen", "fix")];
  if (await runStep(args)) await invoke("open_path", { path: page });
});
action("use-takes", useTakes);
