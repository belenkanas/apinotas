pipeline {
    agent any
 
    options {
        timestamps()
    }
 
    parameters {
        string(name: 'VERSION', defaultValue: '1.0.0', description: 'Version a desplegar')
        booleanParam(name: 'EJECUTAR_TESTS', defaultValue: true, description: 'Correr los tests')
    }
 
    stages {
        stage('Info') {
            steps {
                echo "Rama: ${env.BRANCH_NAME}"
                echo "PR: ${env.CHANGE_ID ?: 'no es un PR'}"
                echo "Rama destino del PR: ${env.CHANGE_TARGET ?: '-'}"
                sh 'git log -1 --oneline'
            }
        }
 
        stage('Instalar dependencias') {
            steps {
                sh '''
                    python3 -m venv .venv
                    . .venv/bin/activate
                    pip install --quiet -r requirements.txt
                '''
            }
        }
 
        stage('Lint') {
            steps {
                sh '''
                    . .venv/bin/activate
                    ruff check .
                '''
            }
        }
 
        stage('Test') {
            when {
                expression { params.EJECUTAR_TESTS }
            }
            steps {
                sh '''
                    . .venv/bin/activate
                    pytest --junitxml=reports/junit.xml
                '''
            }
        }
 
        stage('Deploy') {
            when {
                branch 'main'
            }
            steps {
                echo "Desplegando ${params.VERSION} desde main"
            }
        }
    }
 
    post {
        always {
            junit allowEmptyResults: true, testResults: 'reports/junit.xml'
        }
    }
}