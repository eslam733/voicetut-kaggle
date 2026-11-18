Stand-ins for the GPU libraries the notebooks use (torch, soundfile, voicetut_tts, qwen_asr), so
tests/test_dry_run.py can run the generated notebooks' code on any machine. A "recording" is a
text file holding the sentence as spoken; the fake recognizer reads it back. A first take of a
question (no random seed set yet) comes out wrong, so the check's re-takes get exercised.
