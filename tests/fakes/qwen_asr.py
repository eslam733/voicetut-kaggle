class _Heard:
    def __init__(self, text):
        self.text = text


class Qwen3ASRModel:
    @classmethod
    def from_pretrained(cls, name, dtype, device_map):
        return cls()

    def transcribe(self, audio, language):
        return [_Heard(open(path, encoding="utf-8").read()) for path in audio]
