"""Count the prose words in a Markdown file (code blocks, inline code, URLs and HTML comments excluded).

    py -3.11 tools/count_words.py README.md
"""
import re
import sys
from pathlib import Path


def prose_words(markdown):
    text = re.sub(r"<!--.*?-->", " ", markdown, flags=re.S)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)          # fenced code and commands
    text = re.sub(r"`[^`]*`", " ", text)                        # inline code, file names, commands
    text = re.sub(r"\]\([^)]*\)", "]", text)                    # link targets
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"^\s*\|?\s*:?-{3,}.*$", " ", text, flags=re.M)  # table rules
    return [t for t in re.split(r"[\s|*#>]+", text) if re.search(r"[A-Za-z0-9]", t)]


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "README.md")
    print(len(prose_words(path.read_text(encoding="utf-8"))))
