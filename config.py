import json
import os
from pathlib import Path

USERS_DIR = Path(__file__).parent / "users"
USERS_DIR.mkdir(exist_ok=True)

FILTERED_XML = Path(__file__).parent / "madrid_es_filtered.xml"

TIME_RANGES = {
    "1": ("Esta semana", 7),
    "2": ("Esta semana y la siguiente", 14),
    "3": ("Esta semana, siguiente y la siguiente", 21),
}

FREQUENCIES = {
    "1": ("Resultado diario", "daily"),
    "2": ("Lunes, Miércoles, Viernes", "mwf"),
    "3": ("Solamente los lunes", "mondays"),
}


def user_path(user_id: int) -> Path:
    return USERS_DIR / f"{user_id}.json"


def load_user_config(user_id: int) -> dict | None:
    path = user_path(user_id)
    if path.exists():
        return json.loads(path.read_text())
    return None


def save_user_config(user_id: int, config: dict):
    user_path(user_id).write_text(json.dumps(config, indent=2, ensure_ascii=False))


def delete_user_config(user_id: int):
    path = user_path(user_id)
    if path.exists():
        path.unlink()
