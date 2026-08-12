from pathlib import Path
from unittest.mock import patch

import pytest
from app.main import app
from app.session import create_session_credentials
from fastapi.testclient import TestClient

client = TestClient(app)


def test_get_file_content_success(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-testfile123"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo" / "app"
        repo_dir.mkdir(parents=True, exist_ok=True)
        file_path = repo_dir / "main.py"
        file_path.write_text("print('hello world')", encoding="utf-8")

        client.cookies.set(f"session_secret_{session_id}", secret)
        res = client.get(
            f"/api/file?session_id={session_id}&file_path=app/main.py",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["content"] == "print('hello world')"
        assert data["file_path"] == "app/main.py"


def test_get_file_content_path_traversal_prevention(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-traversal123"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/file?session_id={session_id}&file_path=../session_meta.json",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 403
        assert "Path traversal attempt detected" in res.json()["detail"]


def test_get_file_content_file_not_found(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-notfound123"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/file?session_id={session_id}&file_path=nonexistent.py",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 404
        assert "Requested file does not exist" in res.json()["detail"]


def test_get_file_content_git_metadata_blocked(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-gitblock123"
        secret, csrf = create_session_credentials(session_id)

        git_dir = tmp_path / session_id / "repo" / ".git"
        git_dir.mkdir(parents=True, exist_ok=True)
        (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0", encoding="utf-8")

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/file?session_id={session_id}&file_path=.git/config",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 403
        assert "Git metadata is not accessible" in res.json()["detail"]


def test_get_file_content_symlink_blocked(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-symlink123"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("secret_data", encoding="utf-8")

        link_file = repo_dir / "link.txt"
        try:
            link_file.symlink_to(outside_file)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this environment")

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/file?session_id={session_id}&file_path=link.txt",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 403
        assert "Symlinks are not allowed" in res.json()["detail"]


def test_get_file_content_symlink_parent_blocked(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-symlink-parent123"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)

        outside_dir = tmp_path / "outside"
        outside_dir.mkdir(parents=True, exist_ok=True)
        (outside_dir / "secret.txt").write_text("secret_data", encoding="utf-8")

        link_dir = repo_dir / "linkdir"
        try:
            link_dir.symlink_to(outside_dir, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("Symlinks not supported on this environment")

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/file?session_id={session_id}&file_path=linkdir/secret.txt",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 403
        assert "Symlinks are not allowed" in res.json()["detail"]


def test_get_file_content_binary_blocked(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-binary123"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        binary_file = repo_dir / "blob.bin"
        binary_file.write_bytes(b"\x00\x01\x02binary-data")

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/file?session_id={session_id}&file_path=blob.bin",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 415
        assert "Binary or image files are not supported" in res.json()["detail"]


def test_get_file_content_oversize_blocked(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-oversize123"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        big_file = repo_dir / "big.txt"
        big_file.write_bytes(b"a" * 1_048_577)

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/file?session_id={session_id}&file_path=big.txt",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 400
        assert "File size exceeds maximum limit" in res.json()["detail"]


def test_get_file_content_mixed_utf8_replacement(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-mixedutf8"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        mixed_file = repo_dir / "mixed.txt"
        mixed_file.write_bytes(b"hello\n" + (b"a" * 9000) + b"\xfftail")

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/file?session_id={session_id}&file_path=mixed.txt",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        data = res.json()
        assert "\ufffd" in data["content"]


def test_get_tree_content_git_filter(tmp_path: Path):
    with patch("app.session.settings.shared_data_dir", str(tmp_path)):
        session_id = "session-treegit123"
        secret, csrf = create_session_credentials(session_id)

        repo_dir = tmp_path / session_id / "repo"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git").mkdir(parents=True, exist_ok=True)
        (repo_dir / ".gitignore").write_text("*.pyc", encoding="utf-8")
        (repo_dir / ".github").mkdir(parents=True, exist_ok=True)
        (repo_dir / "main.py").write_text("print()", encoding="utf-8")

        client.cookies.set(f"session_secret_{session_id}", secret)

        res = client.get(
            f"/api/tree?session_id={session_id}",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        items = res.json()
        names = [i["name"] for i in items]
        assert ".git" not in names
        assert ".gitignore" in names
        assert ".github" in names
        assert "main.py" in names
