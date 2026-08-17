import threading
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from snapassist.core.state import State
from snapassist.wm.desktop_entries import DesktopEntryResolver


def test_version_and_packaging_metadata_agree():
    from snapassist import __version__

    assert __version__ == "2.0.0.dev0"
    assert 'version = "2.0.0.dev0"' in (ROOT / "pyproject.toml").read_text()
    assert (ROOT / "LICENSE").is_file()
    assert (ROOT / "CHANGELOG.md").is_file()


def test_desktop_entry_name_has_priority(tmp_path):
    (tmp_path / "org.example.Editor.desktop").write_text(
        "[Desktop Entry]\nName=Editor amigable\nStartupWMClass=example-editor\n",
        encoding="utf-8",
    )
    resolver = DesktopEntryResolver([tmp_path])
    assert resolver.resolve("example-editor") == "Editor amigable"
    assert resolver.resolve("org.example.Editor") == "Editor amigable"


def test_state_rejects_mutation_from_ui_thread():
    state = State()
    state.bind_to_current_thread()
    failures = []

    def mutate():
        try:
            state.update_mru(42)
        except RuntimeError as error:
            failures.append(str(error))

    thread = threading.Thread(target=mutate)
    thread.start()
    thread.join()
    assert failures == ["State solo puede mutarse desde el event loop"]
    assert state.get_mru_list() == []
