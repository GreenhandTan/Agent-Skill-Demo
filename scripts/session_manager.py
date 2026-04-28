from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).parent.resolve()


@dataclass(slots=True)
class SessionSnapshot:
    storage_state: dict[str, Any]


class SessionManager:
    def __init__(self, session_state_path: str) -> None:
        path = Path(session_state_path)
        if not path.is_absolute():
            path = _SCRIPTS_DIR / path
        self.session_state_path = path

    def exists(self) -> bool:
        return self.session_state_path.exists()

    def load(self) -> SessionSnapshot | None:
        if not self.session_state_path.exists():
            return None

        with self.session_state_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        if isinstance(payload, dict) and "storage_state" in payload and isinstance(payload["storage_state"], dict):
            storage_state = payload["storage_state"]
        elif isinstance(payload, dict) and "cookies" in payload and "origins" in payload:
            storage_state = payload
        else:
            storage_state = payload

        if not isinstance(storage_state, dict):
            raise ValueError(f"Invalid session storage state in {self.session_state_path}")

        return SessionSnapshot(storage_state=storage_state)

    def save(self, snapshot: SessionSnapshot) -> None:
        self.session_state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.session_state_path.open("w", encoding="utf-8") as file:
            json.dump(snapshot.storage_state, file, ensure_ascii=False, indent=2)

    def remove(self) -> None:
        if self.session_state_path.exists():
            self.session_state_path.unlink()