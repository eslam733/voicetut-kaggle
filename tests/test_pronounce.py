import unittest

from voicetut_kaggle.pronounce import plain, prepare


class FakeNormalizer:
    _lexicon = {"تاني": "تَانِي"}
    _diacritics = {}

    def expand_numbers(self, text):
        return text.replace("3", "تَلَاتَة")


PRONUNCIATION = {
    "words": {"برافو": "بْرَافُو"},
    "phrases": {"خطوة بخطوة": "خُطْوَة بْخُطْوَة"},
    "lines": {"ممكن تعيد تاني؟": "مُمْكِن تْعِيد تَانِي؟"},
}


class Prepare(unittest.TestCase):
    def test_words_come_from_the_file_then_from_voicetut(self):
        self.assertEqual(prepare("برافو تاني", FakeNormalizer(), PRONUNCIATION), "بْرَافُو تَانِي")

    def test_whole_line_wins_even_when_the_sentence_has_marks(self):
        self.assertEqual(prepare("مُمكن تعيد تاني؟", FakeNormalizer(), PRONUNCIATION), "مُمْكِن تْعِيد تَانِي؟")

    def test_phrases_and_arabic_digits(self):
        said = prepare("٣ خطوة بخطوة", FakeNormalizer(), PRONUNCIATION)
        self.assertEqual(said, "تَلَاتَة خُطْوَة بْخُطْوَة")

    def test_unknown_words_stay_as_written(self):
        self.assertEqual(prepare("كلمة", FakeNormalizer(), {}), "كلمة")

    def test_plain_drops_marks_and_converts_digits(self):
        self.assertEqual(plain(" صَحّ ٣ "), "صح 3")


if __name__ == "__main__":
    unittest.main()
