def write(path, wav, sampling_rate):
    with open(path, "w", encoding="utf-8") as f:
        f.write(wav)
