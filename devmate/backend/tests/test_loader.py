"""
Unit tests for the document loader - no fastAPI, no TestClient, just plain
pytest exercising app.ingestion.document_loader directly
"""

from app.ingestion.document_loader import load_documents_from_folder

VALID_DOC = (
    "id: 1\n"
    "title: Test Doc\n"
    "category: Wiki\n"
    "owner_id: 100\n"
    "last_reviewed_at: 2026-01-01\n"
    "---\n"
    "Body text. \n"
)

def test_loads_valid_documents(tmp_path):
    """
    tmp_path is a built-in pytest fixture: a fresh, empty temporary directory, unique
    to this one test, and deleted automatically aferward. Using it here (rather than
    pointing to a real doc/ folder) is what makes it a true unit test that is completely
    isolated and nothing about it depends on anything currently in our docs/ folder
    """
    (tmp_path / "good.md").write_text(VALID_DOC, encoding="utf-8")

    documents = load_documents_from_folder(tmp_path)

    assert len(documents) == 1
    assert documents[0].title == "Test Doc"


def test_skips_unsupported_file_type(tmp_path, capsys):
    (tmp_path / "notes.txt").write_text("Just some text", encoding="utf-8")

    documents = load_documents_from_folder(tmp_path)
    assert documents == []
    """
    capsys is another built-in pytest fixture: it captures anything printed to
    stdout/stderr during the test, so a plain print(..) such as the loader's
    SKIPPED message, can be asserted directly, the same way a return value
    would be.
    """
    captured = capsys.readouterr()
    assert "unsupported file type" in captured.out

def test_skips_document_missing_required_field(tmp_path, capsys):
    missing_owner = (
        "id: 2\n"
        "title: Missing Owner\n"
        "category: Wiki\n"
        "last_reviewed_at: 2026-01-01\n"
        "---\n"
        "Body.\n"
    )
    (tmp_path / "broken.md").write_text(missing_owner, encoding="utf-8")

    documents = load_documents_from_folder(tmp_path)
    assert documents == []
    captured = capsys.readouterr()
    assert "owner_id" in captured.out

def test_skips_document_with_invalid_category(tmp_path, capsys):
    bad_category = (
        "id: 3\n"
        "title: Bad Category\n"
        "category: Notarealcategory\n"
        "owner_id: 100\n"
        "last_reviewed_at: 2026-01-01\n"
        "---\n"
        "Body.\n"
    )
    (tmp_path / "bad-category.md").write_text(bad_category, encoding="utf-8")

    documents = load_documents_from_folder(tmp_path)
    assert documents == []
    captured = capsys.readouterr()
    assert "unknown category" in captured.out

def test_one_bad_file_does_not_block_the_rest(tmp_path):
    (tmp_path / "good.md").write_text(VALID_DOC, encoding="utf-8")
    (tmp_path / "bad.txt").write_text("Nope", encoding="utf-8")

    documents = load_documents_from_folder(tmp_path)

    assert len(documents) == 1
    assert documents[0].title == "Test Doc"

def text_empty_folder_returns_empty_list(tmp_path):
    assert load_documents_from_folder(tmp_path) == []