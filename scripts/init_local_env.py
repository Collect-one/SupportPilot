import csv
import os
import secrets
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path.home() / "Desktop"
LABELS = {"apiKey", "openAiCompatible", "dashScope", "workspaceId"}


def read_values(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [[cell.strip() for cell in row] for row in csv.reader(handle)]
    values: dict[str, str] = {}
    for row_index, row in enumerate(rows):
        for column_index, cell in enumerate(row):
            if cell not in LABELS:
                continue
            candidates = row[column_index + 1 :]
            if row_index + 1 < len(rows) and column_index < len(rows[row_index + 1]):
                candidates.append(rows[row_index + 1][column_index])
            value = next((candidate for candidate in candidates if candidate), "")
            if value:
                values[cell] = value
    return values


def load_existing(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"')
    return result


def dotenv_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> None:
    candidates = sorted(DESKTOP.glob("*.csv"), key=lambda item: item.stat().st_mtime, reverse=True)
    values: dict[str, str] = {}
    for candidate in candidates:
        try:
            candidate_values = read_values(candidate)
        except (OSError, UnicodeError, csv.Error):
            continue
        if {"apiKey", "openAiCompatible"} <= candidate_values.keys():
            values = candidate_values
            break
    if not values:
        raise SystemExit("未在桌面 CSV 中找到 apiKey 和 openAiCompatible 字段")

    env_path = ROOT / ".env"
    existing = load_existing(env_path)
    endpoint = values["openAiCompatible"].rstrip("/")
    api_key = values["apiKey"]
    config = {
        "DATABASE_URL": "postgresql+psycopg://support_pilot:support_pilot@db:5432/support_pilot",
        "JWT_SECRET": existing.get("JWT_SECRET") or secrets.token_urlsafe(48),
        "ACCESS_TOKEN_MINUTES": "480",
        "ENVIRONMENT": "development",
        "DEMO_MODE": "true",
        "AUTO_CREATE_TABLES": "false",
        "SEED_DEMO": "true",
        "UPLOAD_DIR": "/data/uploads",
        "APP_BASE_URL": f"http://localhost:{os.getenv('SUPPORTPILOT_FRONTEND_PORT', existing.get('FRONTEND_PORT', '8080'))}",
        "FRONTEND_PORT": os.getenv(
            "SUPPORTPILOT_FRONTEND_PORT", existing.get("FRONTEND_PORT", "8080")
        ),
        "LLM_BASE_URL": endpoint,
        "LLM_API_KEY": api_key,
        "LLM_MODEL": "qwen3.7-plus",
        "LLM_ENABLE_THINKING": "false",
        "EMBEDDING_BASE_URL": endpoint,
        "EMBEDDING_API_KEY": api_key,
        "EMBEDDING_MODEL": "qwen3.7-text-embedding",
        "EMBEDDING_DIMENSIONS": "1024",
        "FEISHU_WEBHOOK_URL": existing.get("FEISHU_WEBHOOK_URL", ""),
        "FEISHU_WEBHOOK_SECRET": existing.get("FEISHU_WEBHOOK_SECRET", ""),
    }
    contents = "\n".join(f"{key}={dotenv_value(value)}" for key, value in config.items()) + "\n"
    env_path.write_text(contents, encoding="utf-8")
    print("已从桌面业务空间 CSV 写入本地 .env；密钥值未输出。")


if __name__ == "__main__":
    main()
