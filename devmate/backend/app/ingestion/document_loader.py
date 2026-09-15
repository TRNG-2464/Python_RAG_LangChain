"""
File-based Document Loader

Reads every file in a folder and turns the supported ones into Document objects, replacing
our hardcoded seed data function as the source of truth for our domain models.
"""

from datetime import date
from pathlib import Path #this is the modern object-oriented way to work with file paths(ex: os.path.json)

from app.core.exceptions import DocumentLoadError, UnsupportedFileTypeError
from app.models import Document, DocumentCategory


"""
this is a constant tuple for the formatter keys to define what every document file must have.
We will be referencing this constant in a check rather than adding the required fields manually,
by hand each time we need to check.
"""
REQUIRED_FIELDS = ("id", "title", "category", "owner_id", "last_reviewed_at")

def _parse_frontmatter(text: str, source: Path) -> tuple[dict[str, str], str]:
    """
    Split "key:value" header lines from the body, on the first line that is exactly '---'. 
    returns (fields_dict, body_text)

    Leading underscores in function names is Python's 'internal use only' convention (no private keyword)
    - this helper function isn't meant to be called from outside this module.
    """
    if "---" not in text:
        raise DocumentLoadError(f"{source.name}: missing '---' frontmatter separator.")


    """
    str.partition() splits on the FIRST occurence and returns a 3-tuple: (everything before the separator,
    the separator itself, everything after the separator). The middle value is thrown away here with the '_' -
    it is a naming convention for "this value exists, but I don't need it"
    """
    header_block, _, body = text.partition("---")

    fields: dict[str, str] = {}
    for line in header_block.strip().splitlines():
        if ":" not in line:
            raise DocumentLoadError(f"{source.name}: malformed header line {line!r}")

        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()

    """
    A list comprehension used to build a list of PROBLEMS rather than results -
    return the field that is not in the list of required fields
    """
    missing = [field for field in REQUIRED_FIELDS if field not in fields]
    if missing:
        raise DocumentLoadError(f"{source.name}: missing required field(s) {missing}")

    return fields, body.strip()


def load_one_document(path: Path) -> Document:
    #check the extenstion BEFORE we attempt to read the file (this is much cheaper)
    if path.suffix != ".md":
        raise UnsupportedFileTypeError(
            f"{path.name}: unsupported file type {path.suffix} (only .md is supported)."
        )

    text = path.read_text(encoding="utf-8")
    fields, body = _parse_frontmatter(text, path)

    """
    Each conversion we do here, is wrapped in a try/except block so the error message
    can say exactly WHICH field is bad, instead of a generic 'somthing in this file went wrong'
    """
    try:
        category = DocumentCategory(fields["category"])
    except ValueError as exc:
        """
        "raise...as exc" chains the new exception to the original, allowing our traceback
        to show both, instead of hiding the real low-level cause. This is the Python equivalent
        to Java's 'throw new DocumentLoadError(...).initCause(originalException)'
        """
        raise DocumentLoadError(
            f"{path.name}: unknown category {fields['category']!r}"
        )from exc

    #checks if the last_reviewed_at value is a valid format
    try:
        last_reviewed_at = date.fromisoformat(fields["last_reviewed_at"])
    except ValueError as exc:
        raise DocumentLoadError(
            f"{path.name}: invalid last_reviewed_at date {fields['last_reviewed_at']!r}"
        )from exc

    try:
        document_id = int(fields['id'])
        owner_id = int(fields['owner_id'])
    except ValueError as exc:
        raise DocumentLoadError(
            f"{path.name}: id and owner_id must be integers" 
        )from exc

    return Document(document_id, fields["title"], category, body, owner_id, last_reviewed_at)

def load_documents_from_folder(folder_path: str | Path) -> list[Document]:
    folder = Path(folder_path)
    documents: list[Document] = []

    for path in sorted(folder.iterdir()):
        if path.is_dir():
            continue
        try:
            documents.append(load_one_document(path))
        except DocumentLoadError as exc:
            print(f" SKIPPED {path.name}: {exc}")

    return documents