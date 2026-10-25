"""UTF-8 file output with replacement only after a complete successful write."""
import os
from pathlib import Path
import tempfile


def write_report(filename: str, text: str) -> Path:
    try:
        path = Path(filename).expanduser()
    except (RuntimeError, ValueError) as e:
        raise OSError("Invalid output path or unknown home directory") from e
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, delete=False) as stream:
            temporary = stream.name
            stream.write(text)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return path
