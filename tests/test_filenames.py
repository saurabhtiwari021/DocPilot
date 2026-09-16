from app.services.filenames import safe_filename


def test_strips_unix_traversal():
    assert safe_filename("../../etc/passwd") == "passwd"


def test_strips_windows_traversal():
    assert safe_filename("..\\..\\Windows\\System32\\config") == "config"


def test_strips_absolute_path():
    assert safe_filename("/etc/passwd") == "passwd"


def test_keeps_ordinary_filename():
    assert safe_filename("resume.pdf") == "resume.pdf"


def test_keeps_spaces_and_dashes():
    assert safe_filename("My Resume - 2026.pdf") == "My Resume - 2026.pdf"


def test_strips_unsafe_characters():
    result = safe_filename("weird<>:name?.txt")
    assert "<" not in result and ">" not in result and ":" not in result and "?" not in result
    assert result.endswith(".txt")


def test_empty_filename_gets_a_fallback_name():
    result = safe_filename("")
    assert result  # non-empty
    assert "/" not in result and "\\" not in result


def test_dots_only_filename_gets_a_fallback_name():
    result = safe_filename("...")
    assert result
    assert result != "."
    assert result != ".."
