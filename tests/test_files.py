"""Tests for file I/O tools."""

from pathlib import Path

from src.tools.files import list_directory, read_file, write_file


class TestReadFile:
    def test_reads_content(self, tmp_path):
        file = tmp_path / "test.py"
        file.write_text("def hello(): return 'world'\n", encoding="utf-8")

        result = read_file.invoke({"file_path": str(file)})
        assert result["content"] == "def hello(): return 'world'\n"
        assert result["line_count"] == 1
        assert result["file_path"] == str(file)

    def test_file_not_found(self):
        result = read_file.invoke({"file_path": "/nonexistent/path.py"})
        assert "error" in result


class TestWriteFile:
    def test_writes_new_file(self, tmp_path):
        file = tmp_path / "output.py"
        result = write_file.invoke(
            {"file_path": str(file), "content": "x = 1\n", "mode": "w"}
        )
        assert result["success"] is True
        assert file.read_text() == "x = 1\n"

    def test_append_mode(self, tmp_path):
        file = tmp_path / "append_test.py"
        file.write_text("x = 1\n")

        write_file.invoke({"file_path": str(file), "content": "y = 2\n", "mode": "a"})
        assert file.read_text() == "x = 1\ny = 2\n"


class TestListDirectory:
    def test_lists_py_files(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "b.py").write_text("")
        (tmp_path / "readme.txt").write_text("")

        result = list_directory.invoke({"path": str(tmp_path)})
        py_files = [f for f in result["files"] if f.endswith(".py")]
        assert len(py_files) >= 2

    def test_respects_pattern(self, tmp_path):
        (tmp_path / "a.py").write_text("")
        (tmp_path / "readme.txt").write_text("")

        result = list_directory.invoke({"path": str(tmp_path), "pattern": "*.txt"})
        assert len(result["files"]) >= 1
