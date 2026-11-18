"""Step 8: app-ready audio. Turns the checked FLAC clips into small Opus files (WebM or Ogg),
mono at `export.bitrate`, and writes lines.json so the app knows which clip says what.

Output: <out>/<speaker>/<nnn>.<webm|ogg> and <out>/lines.json ({speaker: [sentence, ...]}).
"""
import json
import os
import shutil
import subprocess
import tempfile
import zipfile


def export(cfg, zip_path, out_dir):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg was not found: install it (e.g. `sudo apt install ffmpeg`)")
    fmt, bitrate = cfg.export["format"], str(cfg.export["bitrate"])
    with zipfile.ZipFile(zip_path) as z:
        names = set(z.namelist())
        missing = [f"{s}/{n:03d}" for s in cfg.speaker_ids() for n in range(len(cfg.lines(s)))
                   if f"voices/{s}/{n:03d}.flac" not in names]
        if missing:
            raise ValueError(f"{zip_path} lacks {len(missing)} clip(s), e.g. {missing[:5]}")
        shutil.rmtree(out_dir, ignore_errors=True)
        with tempfile.TemporaryDirectory() as work:
            source = os.path.join(work, "line.flac")
            for speaker in cfg.speaker_ids():
                os.makedirs(os.path.join(out_dir, speaker))
                for n in range(len(cfg.lines(speaker))):
                    with open(source, "wb") as f:
                        f.write(z.read(f"voices/{speaker}/{n:03d}.flac"))
                    subprocess.run(
                        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", source,
                         "-ac", "1", "-c:a", "libopus", "-b:a", bitrate, "-application", "voip",
                         "-map_metadata", "-1", "-f", fmt, os.path.join(out_dir, speaker, f"{n:03d}.{fmt}")],
                        check=True)
                print(f"{speaker}: {len(cfg.lines(speaker))} clips")
    with open(os.path.join(out_dir, "lines.json"), "w", encoding="utf-8") as f:
        json.dump({s: cfg.lines(s) for s in cfg.speaker_ids()}, f, ensure_ascii=False, indent=1)
    size = sum(os.path.getsize(os.path.join(d, x)) for d, _, files in os.walk(out_dir) for x in files)
    print(f"{out_dir}: {size / 1e6:.1f} MB")
