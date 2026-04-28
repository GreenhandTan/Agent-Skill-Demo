from __future__ import annotations

from browser_adapter import BrowserAdapter
from session_manager import SessionManager, SessionSnapshot


class SessionFlow:
    def __init__(self, browser: BrowserAdapter, session_manager: SessionManager) -> None:
        self.browser = browser
        self.session_manager = session_manager

    def try_restore(self) -> bool:
        snapshot = self.session_manager.load()
        if snapshot is None:
            print("[session] no persisted session found")
            return False

        print("[session] persisted session found, attempting restore")
        return self.browser.restore_session(snapshot)

    def capture_after_login(self) -> SessionSnapshot:
        snapshot = self.browser.capture_session()
        self.session_manager.save(snapshot)
        print("[session] session snapshot persisted")
        return snapshot