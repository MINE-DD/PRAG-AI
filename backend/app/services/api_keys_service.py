import json
from pathlib import Path

_KEYS_PATH = Path("/data/api_keys.json")


class ApiKeysService:
    """Manages API keys stored on-disk in the data volume.

    Keys are written to /data/api_keys.json (mounted volume) so they
    persist across container restarts. They are NEVER sent to the frontend —
    only a boolean 'has_key' indicator is exposed.
    """

    def __init__(self, keys_path: Path = _KEYS_PATH):
        self.keys_path = keys_path

    def _read(self) -> dict:
        if not self.keys_path.exists():
            return {}
        try:
            return json.loads(self.keys_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        self.keys_path.parent.mkdir(parents=True, exist_ok=True)
        self.keys_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def has_key(self, provider: str) -> bool:
        return bool(self._read().get(provider))

    def get_key(self, provider: str) -> str | None:
        return self._read().get(provider) or None

    def set_key(self, provider: str, key: str) -> None:
        data = self._read()
        data[provider] = key
        self._write(data)

    def clear_key(self, provider: str) -> None:
        data = self._read()
        if provider in data:
            del data[provider]
            self._write(data)
