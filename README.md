# catalog

`catalog` is a Python library and CLI for managing and processing media.

The project was initially conceived to facilitate batch transcription of media files (voice notes, specifically) with Whisper.

Its features were designed with this use case in mind, but the working plan is to generalize the library to be useful for a broader range of media types (e.g., images, webpages, API connections).



## Installation

Install with `uv`:
```bash
uv pip install git+https://github.com/jmpaz/catalog.git
```


## Usage

### CLI

The following actions are available via the CLI:
- importing, managing, transcribing, and grouping/tagging media objects
- processing resultant transcriptions ("entries") externally, i.e., with LLMs (not fully implemented)
- searching (keyword, fuzzy, vector) across all entries for a given query
- inspecting media object metadata and entries
- writing Markdown files with the highest-quality textual representation available (LLM-processed transcript > lightly-formatted raw transcript)

For a full list of commands and options, use `catalog --help`.


## Library

`catalog` currently stores:
- metadata and transcriptions in a single JSON file located at `$XDG_CONFIG_HOME/catalog/library.json`.
- copies of imported media files in `~/.local/share/catalog/datastore`.
- embeddings for entry text in `~/.local/share/catalog/embeddings.json`.
