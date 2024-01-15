import unittest
from unittest.mock import patch, mock_open
from utils.conversion import insert_lrc


class TestConversion(unittest.TestCase):
    def test_insert_lrc(self):
        """
        Test to ensure Markdown is prepared correctly with mock LRC content and file name.
        """
        mock_template_content = (
            "---\n"
            "category:\n"
            '  - "[[voice]]"\n'
            "---\n\n"
            "## Transcript\n"
            "```lrc\n"
            "source [[FILE_NAME.ext]]\n\n"
            "LRC_DEST\n"
            "```\n\n"
            "---\n\n"
            "## Notes\n"
            "-"
        )
        mock_lrc_content = (
            "[00:00.0]  This is the first line of text,\n"
            "[00:29.0]  and this is the second.\n"
        )
        audio_filename = "file.wav"

        # Create a custom side_effect function for our mock
        def custom_open(file, mode="r", *args, **kwargs):
            _ = mode, args, kwargs
            if file == "mock_template_path":
                return mock_open(read_data=mock_template_content)()
            elif file == "mock_lrc_file_path":
                return mock_open(read_data=mock_lrc_content)()
            else:
                raise FileNotFoundError(f"No mock for file path: {file}")

        with patch("builtins.open", side_effect=custom_open):
            # Call the function under test
            markdown_content = insert_lrc(
                "mock_lrc_file_path", audio_filename, "mock_template_path"
            )

            # Assert that the markdown content is a string
            self.assertIsInstance(markdown_content, str)

            # Check if the LRC content and audio file name are correctly inserted
            expected_content = mock_template_content.replace(
                "LRC_DEST", mock_lrc_content
            ).replace("[[FILE_NAME.ext]]", f"[[{audio_filename}]]")
            self.assertEqual(markdown_content, expected_content)

            # Print a summary for visual inspection
            print(f"\nGenerated Markdown content:\n{markdown_content}")


if __name__ == "__main__":
    unittest.main()
