"""설정은 환경변수에서 읽는다. 노트북에서는 .env 를 읽고, 배포할 때는 Cloud Run 이 넣어 준다."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOCK_DIR = ROOT / "mock_data"  # 이 폴더 밖의 파일은 읽지 않는다(실제 자료가 섞이지 않게)


def load_dotenv(path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    provider: str
    api_key: str
    model: str
    team_password: str
    daily_limit: int
    env: str
    commit: str
    revision: str


def load_settings():
    load_dotenv(ROOT / ".env")
    provider = os.environ.get("LLM_PROVIDER", "fake").strip().lower()
    settings = Settings(
        provider=provider,
        api_key=os.environ.get("LLM_API_KEY", "").strip(),
        model=os.environ.get("LLM_MODEL", "").strip() or ("fake" if provider == "fake" else "gpt-4o-mini"),
        team_password=os.environ.get("TEAM_PASSWORD", "").strip(),
        daily_limit=int(os.environ.get("DAILY_LIMIT", "300") or 300),
        env=os.environ.get("ENV", "local").strip() or "local",
        commit=os.environ.get("COMMIT_SHA", "local").strip(),
        revision=os.environ.get("K_REVISION", "local"),
    )
    if provider != "fake" and not settings.api_key:
        raise SystemExit("LLM_API_KEY 가 없습니다. 키 없이 화면만 보려면 LLM_PROVIDER=fake 로 둡니다.")
    return settings
