import unittest
from core.process import Processor


class TestProcessor(unittest.TestCase):
    def test_extraction(self):
        """
        Test to ensure LRC text is extracted correctly.
        """
        processor = Processor("outputs/oz/02.lrc")
        processor.read_file()
        lines = processor.extract_lines()

        # Assert that the extracted text is a list
        self.assertIsInstance(lines, list)

        # Print a summary for visual inspection
        print(f"Extracted {len(lines)} items from LRC file.")
        print(f"Samples: {lines[:5]}")

        timestamps = processor.extract_timestamps()
        self.assertIsInstance(timestamps, list)
        print(f"\nThere are {len(timestamps)} timestamps.")
        print(f"Samples: {timestamps[:5]}")

        text = processor.extract_text()
        self.assertIsInstance(text, str)
        print(f"\nThere are {len(text)} chars in the extracted text.")
        print(f"Sample: {text[:100]}")


if __name__ == "__main__":
    unittest.main()
