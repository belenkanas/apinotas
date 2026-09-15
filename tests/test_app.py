import pytest
from fastapi.testclient import TestClient

import app as app_module


@pytest.fixture(autouse=True)
def isolated_notes_file(tmp_path, monkeypatch):
    """Redirige el archivo de notas a una carpeta temporal en cada test."""
    fake_notes_file = tmp_path / "notes.json"
    monkeypatch.setattr(app_module, "NOTES_FILE", fake_notes_file)
    yield


@pytest.fixture
def client():
    return TestClient(app_module.app)

# Endpoints compartidos en v1 y v2

def test_health_check(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_list_notes_empty(client):
    response = client.get("/list")
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_add_note(client):
    response = client.post("/add/1", json={"text": "Comprar leche"})
    assert response.status_code == 201
    assert response.json()["id"] == "1"


def test_add_duplicate_note_fails(client):
    client.post("/add/1", json={"text": "Primera"})
    response = client.post("/add/1", json={"text": "Segunda"})
    assert response.status_code == 409  # o 404 si mantuviste el original


def test_list_after_adding(client):
    client.post("/add/1", json={"text": "Nota A"})
    client.post("/add/2", json={"text": "Nota B"})
    response = client.get("/list")
    assert response.json()["total"] == 2

# Endpoints de v2 solamente

def test_update_note(client):
    client.post("/add/1", json={"text": "Original"})
    response = client.put("/update/1", json={"text": "Editada"})
    assert response.status_code == 200
    assert response.json()["text"] == "Editada"


def test_update_nonexistent_note_fails(client):
    response = client.put("/update/999", json={"text": "No existe"})
    assert response.status_code == 404


def test_delete_note(client):
    client.post("/add/1", json={"text": "A borrar"})
    response = client.delete("/delete/1")
    assert response.status_code == 200

    # Confirmar que ya no aparece en /list
    listado = client.get("/list").json()
    assert "1" not in listado["notes"]


def test_delete_nonexistent_note_fails(client):
    response = client.delete("/delete/999")
    assert response.status_code == 404


def test_note_has_timestamps(client):
    client.post("/add/1", json={"text": "Con metadata"})
    nota = client.get("/list").json()["notes"]["1"]
    assert nota["created_at"] is not None
    assert nota["updated_at"] is not None


def test_backward_compatibility_plain_string_format(client, tmp_path, monkeypatch):
    """v2 debe poder leer notas guardadas en formato viejo (v1: texto plano)."""
    import json
    notes_file = tmp_path / "notes.json"
    notes_file.write_text(json.dumps({"1": "texto plano de v1"}))
    monkeypatch.setattr(app_module, "NOTES_FILE", notes_file)

    response = client.get("/list")
    nota = response.json()["notes"]["1"]
    assert nota["text"] == "texto plano de v1"

# Test de get_instance_suffix()
def test_instance_suffix_from_pod_name(monkeypatch):
    monkeypatch.setenv("POD_NAME", "notas-api-2")
    assert app_module.get_instance_suffix() == "2"


def test_instance_suffix_default_when_no_pod_name(monkeypatch):
    monkeypatch.delenv("POD_NAME", raising=False)
    assert app_module.get_instance_suffix() == "0"


def test_instance_suffix_when_pod_name_has_no_number(monkeypatch):
    monkeypatch.setenv("POD_NAME", "algun-nombre-random")
    assert app_module.get_instance_suffix() == "0"