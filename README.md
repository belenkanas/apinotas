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

## Blue/Green deployment (v1 = blue, v2 = green)

A diferencia del rolling update, acá **blue y green corren al mismo tiempo, completos**, y el cambio de tráfico es instantáneo: se hace cambiando el `selector` de un único Service (`notas-api-prod`), no reemplazando pods de a uno.

Manifest: `k8s/blue-green.yaml` — define dos Deployments (`notas-api-blue` con `notas-api:v1`, `notas-api-green` con `notas-api:v2`), cada uno con su propio `APP_THEME_COLOR` (`azul`/`verde`) para poder distinguirlos a simple vista en las respuestas, más 3 Services: `notas-api-prod` (el de producción, el único que se togglea), y `notas-api-blue-svc`/`notas-api-green-svc` para poder pegarle a cada color por separado sin pasar por producción.

### Desplegar ambos colores

```bash
kubectl apply -f k8s/blue-green.yaml
kubectl get pods -l app=notas-api --show-labels
```

### Hacer el switch de tráfico (blue → green)

En PowerShell, el patch inline con comillas rompe el JSON, así que se usa un archivo de patch en vez de `-p '...'`:

`k8s/patch-green.yaml`:
```yaml
spec:
  selector:
    color: green
```

`k8s/patch-blue.yaml`:
```yaml
spec:
  selector:
    color: blue
```

```powershell
kubectl patch service notas-api-prod --patch-file k8s/patch-green.yaml   # switch a green
kubectl get service notas-api-prod -o jsonpath="{.spec.selector}"        # confirmar el cambio
```

⚠️ Si volvés a correr `kubectl apply -f k8s/blue-green.yaml` (por ejemplo, para editar los Deployments), el `Service notas-api-prod` incluido en ese mismo archivo **vuelve a quedar en `blue`**, pisando cualquier patch que hayas aplicado antes. Hay que reaplicar el patch de green después de cada `apply` si se sigue iterando sobre los Deployments.

⚠️ Si tenés un `kubectl port-forward svc/notas-api-prod ...` abierto de una sesión anterior, se queda pegado al pod que estaba activo en ese momento y no refleja el nuevo selector — hay que cortarlo (Ctrl+C) y abrirlo de nuevo después de cada switch.

### Simular un error en producción y hacer rollback

Con un error detectado en green (real, con una branch con bug intencional, o simulado/narrado), el rollback es instantáneo porque blue nunca dejó de correr:

```powershell
kubectl patch service notas-api-prod --patch-file k8s/patch-blue.yaml
curl.exe http://localhost:8000/     # confirma que volvió a v1 / azul
```

Este es el punto clave frente al rollback de un rolling update: acá no hay que esperar a que se levanten pods de nuevo, solo se corta el tráfico hacia green y vuelve a blue al instante.

## Tests unitarios

`tests/test_app.py` usa `pytest` + `TestClient` de FastAPI. El archivo de notas se aísla con un fixture (`monkeypatch` sobre `NOTES_FILE`) para no tocar el `notes.json` real ni pisar datos entre tests. `v1` tiene los tests de los endpoints compartidos (`/`, `/add`, `/list`) más los de `get_instance_suffix()`; `v2` agrega los de `/update`, `/delete` y compatibilidad hacia atrás con notas en formato de texto plano.

Instalar dependencias de test (separadas de las de producción, en `requirements-dev.txt`):

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

Correr:

```bash
python -m pytest -v
```

`DATA_DIR` es configurable por variable de entorno (`os.environ.get("DATA_DIR", "/data")`), para poder correr los tests fuera de Docker sin permisos sobre `/data`.

## CI/CD con Jenkins

Pipeline declarativo (`Jenkinsfile` en la raíz de cada branch) con 3 stages: instalar dependencias, correr tests, buildear la imagen Docker. Alcance de esta actividad: solo tests + build, sin push a registry ni despliegue automático a k8s.

```groovy
pipeline {
    agent any

    environment {
        IMAGE_NAME = "notas-api"
        IMAGE_TAG  = "${env.BRANCH_NAME}"
    }

    stages {
        stage('Install dependencies') {
            steps {
                sh '''
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install -r requirements.txt
                    pip install -r requirements-dev.txt
                    pip list
                '''
            }
        }

        stage('Run unit tests') {
            steps {
                sh '''
                    . venv/bin/activate
                    export DATA_DIR=$(pwd)/test-data
                    pytest -v
                '''
            }
        }

        stage('Build Docker Image') {
            steps {
                sh "docker build -t ${IMAGE_NAME}:${IMAGE_TAG} ."
            }
        }
    }

    post {
        always {
            echo "Pipeline finalizado para la branch ${env.BRANCH_NAME}"
        }
        failure {
            echo "Los tests fallaron o el build de la imagen falló"
        }
    }
}
```

### Setup de Jenkins (corriendo en Docker)

Jenkins corre como contenedor (`jenkins/jenkins:lts-jdk21`) vía `docker run` directo, reconstruido como imagen custom con Python y Docker CLI instalados, reutilizando el volumen `jenkins_home` existente:

```dockerfile
FROM jenkins/jenkins:lts-jdk21
USER root
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv docker.io \
    && rm -rf /var/lib/apt/lists/*
USER jenkins
```

```powershell
docker build -t jenkins-con-tools .
docker stop jenkins; docker rm jenkins
docker run -d --name jenkins `
    -p 8080:8080 -p 50000:50000 `
    -v jenkins_home:/var/jenkins_home `
    -v /var/run/docker.sock:/var/run/docker.sock `
    jenkins-con-tools
```

El socket de Docker se monta para que Jenkins pueda ejecutar `docker build` usando el Docker del host (Docker-outside-of-Docker). Esto suele requerir ajustar permisos (el usuario `jenkins` necesita pertenecer al grupo dueño del socket, o como arreglo temporal: `docker exec -u root jenkins chmod 666 /var/run/docker.sock`).

### Tipo de job

Se usa **Multibranch Pipeline** (un pipeline por cada branch del repo con `Jenkinsfile`, `v1` y `v2`). Con acceso anónimo a la API de GitHub, el escaneo de branches puede toparse con el rate limit (60 req/hora) — se resuelve agregando un Personal Access Token de GitHub como credencial en Jenkins. Para probar una branch puntual sin depender del escaneo completo, también sirve un job tipo "Pipeline" simple con "Pipeline script from SCM" apuntando a `*/v1`.

### Problemas encontrados y solución

- **`requirements-dev.txt` vacío o no commiteado** → `pytest: not found` sin error explícito de `pip`.
- **`DATA_DIR` hardcodeado a `/data`** → `PermissionError` al importar `app.py` fuera de Docker; se resolvió haciéndolo configurable por env var.
- **Permiso denegado en `/var/run/docker.sock`** → el usuario `jenkins` no pertenece al grupo dueño del socket; se resuelve con `chmod 666` (temporal) o agregando `jenkins` al grupo con el GID correcto en el Dockerfile (permanente).
