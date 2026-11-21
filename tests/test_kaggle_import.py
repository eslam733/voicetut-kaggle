import unittest


class KaggleImport(unittest.TestCase):
    def test_dataset_upload_can_import_kaggle(self):
        from kaggle.models.upload_file import UploadFile

        self.assertTrue(callable(UploadFile))
