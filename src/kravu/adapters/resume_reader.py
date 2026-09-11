"""Read a user's CV file to plain text (setup-time I/O for ``kravu init``).

This adapter does file I/O only — no business logic. Plain-text and Markdown
resumes are read directly; PDF is parsed via ``pypdf`` and DOCX via
``python-docx`` (both core dependencies). Any other format raises an actionable
``ConfigError`` telling the user to supply a supported file.
"""

from __future__ import annotations

from pathlib import Path

from kravu.exceptions import ConfigError

_TEXT_SUFFIXES = frozenset({".txt", ".md", ".markdown", ".text", ""})


def read_resume_text(path: Path) -> str:
    """Return the plain-text contents of a resume file.

    Args:
        path: Path to the user's CV (``.txt``/``.md``/``.pdf``/``.docx``).

    Returns:
        The extracted resume text (stripped of surrounding whitespace).

    Raises:
        ConfigError: The file is missing, empty, or in an unsupported format.
    """
    if not path.exists():
        raise ConfigError(
            f"Resume file not found: {path}. Provide a path to your CV "
            "(.txt, .md, .pdf, or .docx)."
        )

    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8", errors="replace")
    elif suffix == ".pdf":
        text = _read_pdf(path)
    elif suffix == ".docx":
        text = _read_docx(path)
    else:
        raise ConfigError(
            f"Unsupported resume format '{suffix}'. Save your CV as "
            ".txt, .md, .pdf, or .docx and try again."
        )

    text = text.strip()
    if not text:
        raise ConfigError(
            f"Resume file is empty: {path}. Provide a CV with readable text."
        )
    return text


def _read_pdf(path: Path) -> str:
    """Extract text from a PDF resume via ``pypdf``."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: Path) -> str:
    """Extract text from a DOCX resume via ``python-docx``."""
    import docx

    document = docx.Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)
