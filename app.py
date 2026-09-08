from pathlib import Path
import json
import os
import re

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

def get_instance_suffix() -> str:
    pod_name = os.getenv("POD_NAME", "msjapp-0")
    match = re.search(r"-(\d+)$", pod_name)

    if match:
        return match.group(1)

    return "0"


APP_TITLE = os.environ.get("APP_TITLE", "API de notas")
APP_VERSION = os.environ.get("APP_VERSION", "v1")
THEME_COLOR = os.environ.get("APP_THEME_COLOR", "azul")

app = FastAPI(title=APP_TITLE)

DATA_DIR = Path("/data")
NOTES_FILE = DATA_DIR / "notes.json"

# Crea la carpeta si todavía no existe.
DATA_DIR.mkdir(parents=True, exist_ok=True)


class NoteRequest(BaseModel):
    text: str


def load_notes() -> dict[str, str]:
    if not NOTES_FILE.exists():
        return {}

    try:
        with NOTES_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}

    except (json.JSONDecodeError, OSError):
        return {}


def save_notes(notes: dict[str, str]) -> None:
    with NOTES_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            notes,
            file,
            ensure_ascii=False,
            indent=4,
        )


@app.get("/")
def health():
    return {"status": "ok", 
            "version": APP_VERSION, 
            "color": THEME_COLOR}

@app.post("/add/{note_id}", status_code=201)
def add_note(note_id: str, note: NoteRequest):
    notes = load_notes()

    if note_id in notes:
        raise HTTPException(
            status_code=404,
            detail="Ya existe una nota con ese identificador",
        )

    notes[note_id] = note.text
    save_notes(notes)

    return {
        "message": "Nota guardada correctamente",
        "id": note_id,
        "text": note.text,
    }


@app.get("/list")
def list_notes():
    notes = load_notes()

    return {
        "total": len(notes),
        "notes": notes,
    }