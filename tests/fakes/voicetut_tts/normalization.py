class ArabicNormalizer:
    def normalize(self, text):
        return text.replace("٣", "تلاتة").replace("3", "تلاتة")

    def expand_numbers(self, text):
        return self.normalize(text)
