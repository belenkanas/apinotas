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

# Endpoint compartidos en v1 y v2

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