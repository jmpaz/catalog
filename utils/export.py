import os
import re
import yaml
from datetime import datetime


def export_markdown(audio_lrc_pairs, target_path, template_path):
    """
    Exports markdown files for given audio/LRC file pairs.

    :param audio_lrc_pairs: List of tuples containing audio file paths and corresponding LRC file paths.
    :param target_path: Path to the target directory for the markdown files.
    :param template_path: Path to the markdown template.
    """
    if not os.path.exists(target_path):
        os.makedirs(target_path)

    for audio_path, lrc_path in audio_lrc_pairs:
        try:
            created_str, label = parse_file_details(audio_path)
            if created_str is None or label is None:
                raise ValueError(f"Could not parse file details for: {audio_path}")

            lrc_content = extract_lrc_content(lrc_path)
            file_extension = os.path.splitext(audio_path)[1]  # Extract file extension

            # Format strings for the backlink to insert + the output markdown filename
            backlink_str = f"{label if label else os.path.splitext(os.path.basename(audio_path))[0]} ({created_str[:10]}){file_extension}"
            markdown_str = f"{label if label else os.path.splitext(os.path.basename(audio_path))[0]}.md"

            markdown_content = prepare_markdown(
                template_path,
                lrc_content,
                backlink_str,
                created_str,
            )

            markdown_file_path = os.path.join(target_path, markdown_str)
            with open(markdown_file_path, "w") as markdown_file:
                markdown_file.write(markdown_content)

        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")


def parse_file_details(audio_path):
    """
    Parses an audio file path and extracts the date, time, and label (if available).

    :param audio_path: Path to the audio file.
    :param created_str: A string representation of the creation date and time in the format 'YYYY-MM-DDTHH:MM:00'.
    :param label: The descriptive label extracted from the file name, or an empty string if not present.
    """
    file_name = os.path.basename(audio_path)
    parent_dir = os.path.basename(os.path.dirname(audio_path))

    # Extracting time and label from the file name
    match = re.match(r"(\d{2}-\d{2}-\d{2})\s*(.*?)\.\w{3,4}", file_name)
    if not match:
        return None, None  # Return None if format doesn't match

    time_str, label = match.groups()
    label = label.strip()

    # Formatting date and time
    date_str = datetime.strptime(parent_dir, "%Y-%m-%d").strftime("%Y-%m-%dT")
    time_str = ":".join(time_str.split("-")[:2]) + ":00"  # Format time as HH:MM:00

    return (
        date_str + time_str,
        label,
    )


def prepare_markdown(template_src, lrc_str, backlink_str, created_str=None):
    """
    Injects LRC content into a markdown template, updates the 'created' frontmatter if provided,
    and ensures no 'null' values in the YAML frontmatter.

    :param template_src: Path to the markdown template with 'LRC_DEST' and '[[FILE_NAME.ext]]' placeholders.
    :param lrc_str: LRC file content.
    :param backlink_str: Name of the file reference to be inserted.
    :param created_str: (Optional) Creation datetime string in 'YYYY-MM-DDTHH:MM:00' format to be injected into the frontmatter.

    :return: Processed markdown content as a string.
    """
    if not os.path.exists(template_src):
        raise FileNotFoundError(f"Template file not found: {template_src}")

    template = open(template_src, "r").read()
    markdown_content = template.replace(
        "[[FILE_NAME.ext]]", f"[[{backlink_str}]]"
    ).replace("LRC_DEST", lrc_str)

    # Find frontmatter block
    frontmatter_match = re.search(r"^---\n(.+?)\n---", markdown_content, re.DOTALL)
    if frontmatter_match:
        frontmatter_str = frontmatter_match.group(1)
        frontmatter = yaml.safe_load(
            frontmatter_str
        )  # Convert frontmatter string to dictionary

        # Inject or update 'created' property if needed
        if created_str:
            frontmatter["created"] = created_str

        # Dump the updated frontmatter back to string ensuring no null values
        frontmatter_str_updated = yaml.dump(
            frontmatter, default_flow_style=False, sort_keys=False
        ).rstrip()
        frontmatter_str_updated = frontmatter_str_updated.replace(
            "null", '""'
        )  # Replace null with empty string

        markdown_content = markdown_content.replace(
            frontmatter_match.group(0), f"---\n{frontmatter_str_updated}\n---"
        )

    return markdown_content


def extract_lrc_content(lrc_file_path):
    """
    Extracts the LRC content from a file and returns it as a string.
    """
    if not os.path.exists(lrc_file_path):
        raise FileNotFoundError(f"LRC file not found: {lrc_file_path}")
    else:
        with open(lrc_file_path, "r") as target_lrc:
            lrc_str = target_lrc.read()
            return lrc_str
