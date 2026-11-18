import os

import torch

from .normalization import ArabicNormalizer


class _Normalizer(ArabicNormalizer):
    _lexicon = {}
    _diacritics = {}


class VoiceTutTTS:
    sampling_rate = 24000
    normalizer = _Normalizer()

    @classmethod
    def from_pretrained(cls, name, device, dtype):
        return cls()

    def synthesize(self, text, num_step, normalize, **voice):
        assert normalize is False, "the notebooks vowel the text themselves"
        assert len(voice) in (1, 2), voice
        if "ref_audio" in voice:
            assert os.path.isfile(voice["ref_audio"]) and voice["ref_text"]
        return "غلط" if torch.SEED is None and "؟" in text else text
