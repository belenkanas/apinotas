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