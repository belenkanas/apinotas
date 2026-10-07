from __future__ import annotations
 
import json
import os
import random
import re
import time
from pathlib import Path
 
from fastapi import FastAPI, HTTPException, Request, Response
from pydantic import BaseModel
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.routing import Match
 
CONFIG_DIR = Path(os.environ.get("CONFIG_DIR", "/etc/notas-config"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))
NOTES_FILE = DATA_DIR / "notes.txt"
 
DATA_DIR.mkdir(parents=True, exist_ok=True)
 
# ---------------------------------------------------------------------------
# Métricas Prometheus
# ---------------------------------------------------------------------------
 
# Counter: Solo sube cuando se crean notas nuevas desde que arrancó este proceso.
# (se expone como notes_created_total)
NOTES_CREATED = Counter("notes_created", "Total de notas creadas")
 
# Gauge (medidor): Sube y baja según las notas almacenadas ahora mismo.
NOTES_STORED = Gauge("notes_stored", "Cantidad de notas almacenadas actualmente")
 
# Counter e Histogram por método y endpoint
# (el Counter se expone como request_count_total)
request_count = Counter(
    "request_count", "Total de requests", ["method", "endpoint", "status"]
)
request_duration = Histogram(
    "request_duration", "Duración de requests en segundos", ["method", "endpoint"]
)
 
 
# ---------------------------------------------------------------------------
# Configuración por instancia
# ---------------------------------------------------------------------------
 
def get_instance_suffix() -> str:
    pod_name = os.getenv("POD_NAME", "msjapp-0")
    match = re.search(r"-(\d+)$", pod_name)
    return match.group(1) if match else "0"
 
 
def load_instance_config() -> dict:
    config_file = CONFIG_DIR / f"instance-{get_instance_suffix()}.json"
    if not config_file.exists():
        return {}
    try:
        with config_file.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}
 
 
_instance_config = load_instance_config()
 
APP_TITLE = _instance_config.get("title", os.environ.get("APP_TITLE", "API de notas"))
APP_VERSION = os.environ.get("APP_VERSION", "v1")
THEME_COLOR = _instance_config.get("color", os.environ.get("APP_THEME_COLOR", "azul"))
 
app = FastAPI(title=APP_TITLE)
 
 
# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
 
class NoteRequest(BaseModel):
    text: str
 
 
def load_notes() -> dict[str, str]:
    if not NOTES_FILE.exists():
        return {}
    try:
        with NOTES_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}
 
 
def save_notes(notes: dict[str, str]) -> None:
    with NOTES_FILE.open("w", encoding="utf-8") as file:
        json.dump(notes, file, ensure_ascii=False, indent=4)
 
 
# El gauge arranca con el valor real que hay en disco
NOTES_STORED.set(len(load_notes()))
 
 
# ---------------------------------------------------------------------------
# Caos (opcional, controlado por variables de entorno; por defecto desactivado)
# ---------------------------------------------------------------------------
 
def maybe_slow() -> None:
    delay = float(os.environ.get("CHAOS_DELAY_SECONDS", "0"))
    if delay > 0:
        time.sleep(delay)
 
 
def maybe_fail() -> None:
    rate = float(os.environ.get("CHAOS_FAIL_RATE", "0"))
    if rate > 0 and random.random() < rate:
        raise HTTPException(status_code=500, detail="Fallo simulado (chaos)")
 
 
# ---------------------------------------------------------------------------
# Middleware de métricas
# ---------------------------------------------------------------------------
 
def route_template(request: Request) -> str:
    """Devuelve '/add/{note_id}' en vez de '/add/abc' para no explotar la
    cardinalidad de las etiquetas."""
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", request.url.path)
    return "unmatched"
 
 
@app.middleware("http")
async def add_prometheus_metrics(request: Request, call_next):
    start_time = time.perf_counter()
    status = "500"  # si call_next lanza una excepción no controlada
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        duration = time.perf_counter() - start_time
        endpoint = route_template(request)
        request_count.labels(
            method=request.method, endpoint=endpoint, status=status
        ).inc()
        request_duration.labels(
            method=request.method, endpoint=endpoint
        ).observe(duration)
 
# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
 
@app.get("/")
def health():
    return {
        "status": "ok",
        "instance": get_instance_suffix(),
        "version": APP_VERSION,
        "color": THEME_COLOR,
    }
 
 
@app.post("/add/{note_id}", status_code=201)
def add_note_post(note_id: str, note: NoteRequest):
    maybe_slow()
    maybe_fail()
 
    notes = load_notes()
    if note_id in notes:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una nota con ese identificador",
        )
 
    notes[note_id] = note.text
    save_notes(notes)
 
    NOTES_CREATED.inc()
    NOTES_STORED.set(len(notes))
 
    return {
        "message": "Nota guardada correctamente",
        "id": note_id,
        "text": note.text,
        "instance": get_instance_suffix(),
    }
 
 
@app.get("/add/{note}")
def add_note_get(note: str):
    """Atajo para probar desde el navegador / curl: el id se genera solo."""
    maybe_slow()
    maybe_fail()
 
    notes = load_notes()
    next_id = str(max((int(k) for k in notes if k.isdigit()), default=0) + 1)
    notes[next_id] = note
    save_notes(notes)
 
    NOTES_CREATED.inc()
    NOTES_STORED.set(len(notes))
 
    return {
        "message": f"Nota '{note}' agregada correctamente",
        "id": next_id,
        "instance": get_instance_suffix(),
    }
 
 
@app.get("/list")
def list_notes():
    notes = load_notes()
    return {"total": len(notes), "notes": notes}
 
 
@app.get("/metrics")
def get_metrics():
    # Refresca el gauge con lo que hay en disco (útil si varias réplicas
    # comparten el mismo volumen)
    NOTES_STORED.set(len(load_notes()))
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
 
 
@app.get("/chaos")
def chaos():
    maybe_slow()
    maybe_fail()
    return {
        "message": "Chaos endpoint is working",
        "instance": get_instance_suffix(),
    }