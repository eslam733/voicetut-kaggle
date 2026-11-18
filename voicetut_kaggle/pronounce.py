"""Prepares a sentence for VoiceTut so every word is pronounced as intended.

VoiceTut's own normalizer strips all vowel marks (shadda too) before adding its own for a few
words, so "عدّ" is read "عد". The project's pronunciation file gives words their full vowelling
("words"), "phrases" for words said two ways depending on the words around them, and "lines":
whole sentences whose spelling was picked by ear. This reads the numbers in Egyptian Arabic, then
vowels each word from that file (falling back to VoiceTut's own list). The result goes to
synthesize(..., normalize=False).

This file is copied into every generated notebook, so it only uses the standard library.
"""
import re

MARKS = "ً-ْ"
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def plain(text):
    """[text] without vowel marks, with Western digits: how the "lines" keys are written."""
    return re.sub(f"[{MARKS}ـ]", "", text).translate(DIGITS).strip()


def prepare(text, normalizer, pronunciation):
    """[text] as VoiceTut should read it.

    [pronunciation]: {"words": {...}, "phrases": {...}, "lines": {...}} (all optional).
    """
    text = plain(text)
    if text in pronunciation.get("lines", {}):
        return pronunciation["lines"][text]
    for written, said in pronunciation.get("phrases", {}).items():
        text = re.sub(rf"(?<![ء-ي]){re.escape(written)}(?![ء-ي])", said, text)
    text = normalizer.expand_numbers(text)  # numbers come back as vowelled words
    words = pronunciation.get("words", {})

    def word(m):
        w = m.group(0)
        return words.get(w) or normalizer._lexicon.get(w) or normalizer._diacritics.get(w, w)

    # Only runs of plain letters: words already vowelled (phrases, numbers) are left alone.
    out = re.sub(f"[ء-ي{MARKS}]+",
                 lambda m: m.group(0) if re.search(f"[{MARKS}]", m.group(0)) else word(m), text)
    return re.sub(r"\s+", " ", out).strip()
