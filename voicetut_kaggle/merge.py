"""Step 7: add lines recorded later to the voices zip, without misnumbering the old clips.

Line n of a speaker is the shared sentences, then their own. New shared sentences go at the end of
the shared list, so they take numbers FIRST..LAST and every speaker's own lines move up by
LAST-FIRST+1. (With no per-speaker sentences, nothing moves: the new lines are simply appended.)
"""
import re
import zipfile

CLIP = re.compile(r"voices/([^/]+)/(\d{3,})\.flac$")


def merge(base_zip, new_zip, first, last, out_zip):
    """base_zip + new_zip's clips first..last of every speaker -> out_zip."""
    count = last - first + 1
    with zipfile.ZipFile(base_zip) as base, zipfile.ZipFile(new_zip) as new, \
            zipfile.ZipFile(out_zip, "w", zipfile.ZIP_STORED) as out:
        new_names = set(new.namelist())
        speakers = set()
        for name in base.namelist():
            found = CLIP.match(name)
            if not found:
                continue
            speaker, n = found.group(1), int(found.group(2))
            speakers.add(speaker)
            out.writestr(f"voices/{speaker}/{n + count if n >= first else n:03d}.flac", base.read(name))
        missing = [f"{s}/{n:03d}" for s in sorted(speakers) for n in range(first, last + 1)
                   if f"voices/{s}/{n:03d}.flac" not in new_names]
        if missing:
            raise ValueError(f"{new_zip} lacks {len(missing)} new clip(s), e.g. {missing[:5]}")
        for speaker in sorted(speakers):
            for n in range(first, last + 1):
                out.writestr(f"voices/{speaker}/{n:03d}.flac", new.read(f"voices/{speaker}/{n:03d}.flac"))
    print(f"{len(speakers)} speakers, {count * len(speakers)} clips added at {first}-{last} -> {out_zip}")
