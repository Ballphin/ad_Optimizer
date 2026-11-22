"""`.env` 로더 (의존성 없음). 값은 절대 출력하지 않는다."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: str | Path = ROOT / ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.split(" #", 1)[0].split("\t#", 1)[0].strip().strip('"').strip("'")
        env[k.strip()] = v
    return env


def ssl_context():
    """macOS python.org 빌드의 CA 인증서 누락 대응."""
    import ssl
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()
