import os
from .conversion import extract_lrc_content, prepare_markdown


def export_markdown(audio_lrc_pairs, target_path, template_path):
    """
    Exports markdown files for given audio/LRC file pairs.

    :param audio_lrc_pairs: List of tuples containing audio file paths and corresponding LRC file paths.
    :param target_path: Path where the markdown files will be saved.
    :param template_path: Path to the markdown template.
    """
    if not os.path.exists(target_path):
        os.makedirs(target_path)

    for audio_path, lrc_path in audio_lrc_pairs:
        try:
            lrc_content = extract_lrc_content(lrc_path)
            markdown_content = prepare_markdown(
                template_path, lrc_content, os.path.basename(audio_path)
            )

            markdown_file_path = os.path.join(
                target_path, os.path.splitext(os.path.basename(audio_path))[0] + ".md"
            )
            with open(markdown_file_path, "w") as markdown_file:
                markdown_file.write(markdown_content)

        except FileNotFoundError as e:
            print(f"Error: {e}")
