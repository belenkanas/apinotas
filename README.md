# API de Notas — FastAPI + Kubernetes

API simple para guardar notas, con dos versiones compatibles entre sí, desplegada en Kubernetes (minikube) como un `StatefulSet` de 3 instancias diferenciadas por `ConfigMap`.

## Estructura del proyecto

```
.
├── app.py                  # código de la API (difiere entre branches v1 y v2)
├── Dockerfile
├── docker-compose.yml      # para pruebas locales sin k8s
├── requirements.txt
└── k8s/
    ├── configmap.yaml      # valores distintos por instancia (title, color)
    └── statefulset.yaml    # StatefulSet + Service headless + Service NodePort
```

`k8s/` vive únicamente en la branch `main`: es infraestructura, no código de versión de la app.

## Endpoints

| Endpoint                | Método | Versión | Descripción                          |
|--------------------------|--------|---------|---------------------------------------|
| `/`                      | GET    | v1 y v2 | Estado del API + instancia + color    |
| `/add/{note_id}`         | POST   | v1 y v2 | Agrega una nota (`{"text": "..."}`)   |
| `/list`                  | GET    | v1 y v2 | Lista todas las notas                 |
| `/update/{note_id}`      | PUT    | solo v2 | Modifica el texto de una nota         |
| `/delete/{note_id}`      | DELETE | solo v2 | Elimina una nota                      |

**Compatibilidad v1 ↔ v2:** los endpoints de v1 no cambian de contrato. v2 solo agrega funcionalidad (`/update`, `/delete`) y enriquece `/list` con metadata (`created_at`, `updated_at`). v2 puede leer notas guardadas por v1 (formato de texto plano) gracias a `normalize_note()`.

## Diferenciación por instancia (ConfigMap)

Cada réplica del `StatefulSet` tiene un nombre ordinal predecible (`notas-api-0`, `notas-api-1`, `notas-api-2`). La app lee su propio nombre vía la variable de entorno `POD_NAME` (downward API), extrae el sufijo numérico, y carga su configuración desde `/etc/notas-config/instance-{sufijo}.json`, montado desde el `ConfigMap` `notas-api-config`.

## Uso local (Docker Compose)

```bash
docker compose up --build
curl http://localhost:8000/
```

## Despliegue en minikube

```bash
minikube start --driver=docker
eval $(minikube docker-env)          # PowerShell: minikube docker-env | Invoke-Expression

git checkout v1 && docker build -t notas-api:v1 .
git checkout v2 && docker build -t notas-api:v2 .
git checkout main

kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/statefulset.yaml   # levanta con notas-api:v1
kubectl get pods                        # notas-api-0/1/2
```

Probar cada instancia por separado:

```bash
kubectl port-forward notas-api-0 8001:8000
curl.exe http://localhost:8001/
```

## Rolling update (v1 → v2)

```bash
kubectl set image statefulset/notas-api notas-api=notas-api:v2
kubectl rollout status statefulset/notas-api
```

El `StatefulSet` actualiza los pods de a uno, en orden descendente (`notas-api-2` → `notas-api-1` → `notas-api-0`), gracias a `updateStrategy.type: RollingUpdate`.

Comandos útiles:

```bash
kubectl get pods -w                              # ver el progreso en vivo
kubectl rollout history statefulset/notas-api    # historial de revisiones
kubectl rollout undo statefulset/notas-api       # revertir a la versión anterior
```
