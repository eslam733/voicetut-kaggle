"""Step 5: a local web page to listen to clips side by side.

- From the check's voices_checked.zip: every line the speech recognizer still flags, with what it
  heard and its error score (optionally next to the same line from another zip, e.g. an earlier run).
- From the fix notebook's fix.zip: every spelling and take of each re-recorded clip, next to the
  clip in use now (optionally), to pick the best by ear.
Browsers play FLAC, so the clips are only copied out of the zip.
"""
import html
import json
import os
import shutil
import zipfile
from collections import defaultdict

STYLE = """body{font-family:system-ui,sans-serif;margin:24px;background:#f6f8fa;color:#222}
table{border-collapse:collapse;background:#fff}td,th{padding:10px 12px;border-bottom:1px solid #e3e6ea;
text-align:left;vertical-align:top}.t{font-size:19px}.h{font-size:15px;color:#a0522d;margin-top:4px}
.n{color:#666;font-size:13px}.f{color:#b42318;font-size:13px;font-weight:600}.p{display:flex;align-items:center;gap:6px;margin:4px 0}.p b{width:26px}
audio{width:220px}label.u{font-size:13px;color:#555;cursor:pointer}
#picks{position:sticky;bottom:0;background:#fff;border-top:2px solid #d0d7de;padding:12px;margin-top:16px}
#picks textarea{width:100%;height:58px;font-family:monospace;font-size:13px}"""

# The pick buttons: one choice per row, kept in the browser, turned into the use-take command.
PICKS_JS = """<script>
const KEY='vk-picks:'+location.pathname, cmd=document.getElementById('cmd');
let saved={};try{saved=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function update(){const picks=[...document.querySelectorAll('input.pick:checked')].map(i=>i.value).filter(v=>v);
 const s={};document.querySelectorAll('input.pick:checked').forEach(i=>s[i.name]=i.value);
 try{localStorage.setItem(KEY,JSON.stringify(s))}catch(e){}
 document.getElementById('count').textContent=picks.length;
 cmd.value=picks.length?cmd.dataset.prefix+' '+picks.join(' '):'(pick a take in a row to swap it in)';}
document.querySelectorAll('input.pick').forEach(i=>{if(saved[i.name]!==undefined)i.checked=saved[i.name]===i.value;
 i.addEventListener('change',update)});
document.getElementById('copy').onclick=()=>{cmd.select();try{navigator.clipboard.writeText(cmd.value)}catch(e){document.execCommand('copy')}};
update();
</script>"""


def build(cfg, zip_path, out_dir, compare=None, show_all=False):
    """Writes out_dir/index.html for a voices_checked.zip or a fix.zip; returns its path.

    [compare]: another voices zip to show next to it (for a fix.zip: the clips in use now).
    """
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir)
    if "fix/said.json" in names:
        body = _fix_page(zip_path, out_dir, compare)
    elif "report.json" in names:
        body = _flagged_page(cfg, zip_path, out_dir, compare, show_all)
    else:
        raise ValueError(f"{zip_path} is neither a voices_checked.zip (report.json) nor a fix.zip (said.json)")
    page = os.path.join(out_dir, "index.html")
    with open(page, "w", encoding="utf-8") as f:
        f.write(f"<!doctype html><meta charset=utf-8><title>Listen</title><style>{STYLE}</style>{body}")
    print(f"open {page} in a browser")
    return page


def _copy(zip_path, member, out_dir, name):
    """Copies one clip out of the zip; returns an <audio> tag for it, or a dash if it is missing."""
    with zipfile.ZipFile(zip_path) as z:
        if member not in z.namelist():
            return "<span class=n>-</span>"
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(z.read(member))
    return f"<audio controls preload=none src='{html.escape(name)}'></audio>"


def _flagged_page(cfg, zip_path, out_dir, compare, show_all):
    with zipfile.ZipFile(zip_path) as z:
        report = json.loads(z.read("report.json"))
    threshold = cfg.check["threshold"]
    flagged = {k for k, r in report.items() if r["errors"] > threshold and not r.get("fixed")}
    show_all = show_all or not flagged  # nothing flagged: an empty page helps nobody, show every line
    keys = sorted(report if show_all else flagged)
    rows = []
    for key in keys:
        r, name = report[key], key.replace("/", "_")
        speaker, n = key.split("/")
        other = _copy(compare, f"voices/{key}.flac", out_dir, f"{name}_other.flac") if compare else ""
        if r.get("fixed"):  # swapped in with use-take: the check's scores were for the old clip
            mark, heard = f"<div class=n>re-recorded: {html.escape(r['fixed'])}</div>", ""
            score = "<div class=n>not checked again</div>"
        else:
            mark = "<div class=f>flagged</div>" if show_all and key in flagged else ""
            heard = f"<div dir=rtl class=h>heard: {html.escape(r['heard'])}</div>"
            score = f"<div class=n>error {r['errors']:.2f} · take {r['take']} of {r['takes']}</div>"
        rows.append(
            f"<tr><td class=n>{n}</td><td>{html.escape(speaker)}{mark}"
            f"<div dir=rtl class=t>{html.escape(r['text'])}</div>{heard}</td>"
            f"<td>{_copy(zip_path, f'voices/{key}.flac', out_dir, f'{name}.flac')}{score}</td>"
            + (f"<td>{other}</td>" if compare else "") + "</tr>")
    if not flagged:
        title = f"Every line passed the check ({len(report)} lines)"
    elif show_all:
        title = f"All lines ({len(flagged)} of {len(report)} flagged)"
    else:
        title = f"Lines the recognizer still flags ({len(flagged)} of {len(report)})"
    other_head = f"<th>{html.escape(os.path.basename(compare))}</th>" if compare else ""
    return (f"<h2>{title}</h2><p>Brown: what the speech recognizer heard. Error: share of letters that "
            f"differ (0 = exact; flagged above {threshold}). Many flags are only spelling: trust your ears. "
            "To fix a line, correct its word in the pronunciation file, or try spellings with "
            "<code>vk fix</code>.</p>"
            f"<table><tr><th>Line</th><th></th><th>{html.escape(os.path.basename(zip_path))}</th>{other_head}</tr>"
            + "".join(rows) + "</table>")


def _fix_page(zip_path, out_dir, base):
    with zipfile.ZipFile(zip_path) as z:
        said = json.loads(z.read("fix/said.json"))
    clips = defaultdict(lambda: defaultdict(list))  # (speaker, line) -> variant -> [take names]
    for name, job in sorted(said.items()):
        clips[(job["speaker"], job["line"])][job["variant"]].append(name)
    rows = []
    for (speaker, line), variants in sorted(clips.items()):
        row = f"{speaker}_{line:03d}"
        keep = (f"<label class=u><input type=radio class=pick name='{html.escape(row)}' value='' checked> "
                "keep</label>")
        now = _copy(base, f"voices/{speaker}/{line:03d}.flac", out_dir, f"{speaker}_{line:03d}_now.flac") \
            if base else ""
        cells = []
        for variant, takes in sorted(variants.items()):
            players = "".join(
                f"<div class=p><b>{html.escape(variant)}{said[t]['take']}</b>"
                f"{_copy(zip_path, f'fix/{t}.flac', out_dir, f'{t}.flac')}"
                f"<label class=u><input type=radio class=pick name='{html.escape(row)}' "
                f"value='{html.escape(t)}'> use</label></div>" for t in takes)
            cells.append(f"<td><div dir=rtl class=t>{html.escape(said[takes[0]]['text'])}</div>{players}</td>")
        rows.append(f"<tr><td>{html.escape(speaker)}<div class=n>line {line}</div>{keep}</td>"
                    + (f"<td>{now}</td>" if base else "") + "".join(cells) + "</tr>")
    base_zip = base or "<voices zip>"
    out_zip = (os.path.splitext(base)[0] + "_picked.zip") if base else "<new voices zip>"
    prefix = f"vk use-take {zip_path} {base_zip} {out_zip}"
    return ("<h2>Pick the best take</h2><p>Each column is one spelling, given to the voice exactly as "
            "shown. Press <b>use</b> on the take you like in each row (<b>keep</b> leaves the clip in use "
            "now); your picks are remembered in this browser. Then run the command below.</p><table>"
            + "".join(rows) + "</table>"
            f"<div id=picks><b><span id=count>0</span> picked.</b> Swap them in with:"
            f"<textarea id=cmd readonly data-prefix='{html.escape(prefix)}'></textarea>"
            "<button id=copy>Copy</button></div>" + PICKS_JS)
