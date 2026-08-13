"""Настройки бота. Все значения берутся из переменных окружения (.env)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv() -> None:
    env_file = BASE_DIR.parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass
class Settings:
    token: str
    webapp_url: str = ""
    db_path: str = str(BASE_DIR.parent / "data" / "kitob.sqlite3")
    max_upload_mb: int = 48          # лимит Telegram Bot API на отправку файла — 50 МБ
    results_per_page: int = 6
    admins: list[int] = field(default_factory=list)
    request_timeout: int = 60


def load_settings() -> Settings:
    _load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("BOT_TOKEN не задан. Скопируйте .env.example в .env и впишите токен от @BotFather.")
    admins = [int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()]
    s = Settings(
        token=token,
        webapp_url=os.getenv("WEBAPP_URL", "").strip(),
        admins=admins,
    )
    if os.getenv("DB_PATH"):
        s.db_path = os.environ["DB_PATH"]
    if os.getenv("MAX_UPLOAD_MB", "").isdigit():
        s.max_upload_mb = int(os.environ["MAX_UPLOAD_MB"])
    Path(s.db_path).parent.mkdir(parents=True, exist_ok=True)
    return s
