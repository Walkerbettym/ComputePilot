"""Tests for WorkspaceManager."""

from __future__ import annotations

from pathlib import Path

from computepilot.cli.workspace import WorkspaceManager


class TestWorkspaceManager:
    @staticmethod
    def _make_mgr(tmp_path: Path, name: str = "mgr") -> WorkspaceManager:
        # Isolate the manager to a temp dir
        target = tmp_path / name
        target.mkdir(parents=True, exist_ok=True)
        # Monkey will be applied at call site
        return WorkspaceManager()

    def test_create(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = WorkspaceManager()
        ws = mgr.create("test", str(tmp_path / "ws"), "test workspace")
        assert ws.name == "test"
        assert mgr.active == "test"

    def test_create_duplicate(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = WorkspaceManager()
        mgr.create("dup", str(tmp_path / "ws"))
        import pytest

        with pytest.raises(ValueError, match="already exists"):
            mgr.create("dup", str(tmp_path / "ws2"))

    def test_list(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = WorkspaceManager()
        mgr.create("a", str(tmp_path / "a"))
        mgr.create("b", str(tmp_path / "b"))
        assert len(mgr.list) == 2

    def test_switch(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = WorkspaceManager()
        mgr.create("w1", str(tmp_path / "w1"))
        mgr.create("w2", str(tmp_path / "w2"))
        ws = mgr.switch("w1")
        assert ws is not None
        assert mgr.active == "w1"

    def test_get(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = WorkspaceManager()
        mgr.create("x", str(tmp_path / "x"))
        ws = mgr.get("x")
        assert ws is not None
        assert ws.name == "x"
        assert mgr.get("nonexistent") is None

    def test_remove(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = WorkspaceManager()
        mgr.create("r", str(tmp_path / "r"))
        assert mgr.remove("r") is True
        assert mgr.remove("r") is False
        assert mgr.get("r") is None

    def test_persistence(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        mgr1 = WorkspaceManager()
        mgr1.create("p", str(tmp_path / "p"))
        # Reload from same path
        mgr2 = WorkspaceManager()
        assert mgr2.get("p") is not None
        assert mgr2.active == "p"

    def test_active_path(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        mgr = WorkspaceManager()
        assert mgr.active_path is None
        mgr.create("ap", str(tmp_path / "ap"))
        assert mgr.active_path is not None
        assert mgr.active_path.name == "ap"
