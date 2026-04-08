    // Modular CI Template (Repo-Root): modules.json → Packages + Services, Tree-Tags, partieller Build
    // Skripte: scripts/ci_*.py (Python 3.11+)

    pipeline {
        agent any

        options {
            timestamps()
            timeout(time: 60, unit: 'MINUTES')
        }

        environment {
            DOCKERHUB_CREDS_ID = 'dockerhub-creds'
        }

        stages {
            stage('Checkout') {
                steps {
                    checkout scm
                }
            }

            stage('Fetch git tags') {
                steps {
                    sh '''
                        set -e
                        git remote get-url origin >/dev/null 2>&1 && git fetch origin --tags --force || git fetch --tags --force || true
                        git tag -l 'v*' | tail -5 || true
                    '''
                }
            }

            stage('Resolve version & tree') {
                steps {
                    sh '''
                        set -e
                        python3.11 scripts/ci_resolve_version.py
                        . ./.jenkins_runtime.env
                        echo "SOFTWARE_VERSION=${SOFTWARE_VERSION}"
                    '''
                }
            }

            stage('Build plan') {
                steps {
                    sh '''
                        set -e
                        python3.11 scripts/ci_build_plan.py
                        cat .jenkins_skip_pipeline || true
                    '''
                }
            }

            stage('Cleanup containers') {
                when {
                    expression {
                        return !fileExists('.jenkins_skip_pipeline') || readFile('.jenkins_skip_pipeline').trim() != 'true'
                    }
                }
                steps {
                    sh '''
                        docker container stop $(docker container ls -aq) 2>/dev/null || true
                        docker container rm $(docker container ls -aq) 2>/dev/null || true
                    '''
                }
            }

            stage('Generate Dockerfile') {
                when {
                    expression {
                        return !fileExists('.jenkins_skip_pipeline') || readFile('.jenkins_skip_pipeline').trim() != 'true'
                    }
                }
                steps {
                    sh '''
                        set -e
                        python3.11 scripts/ci_generate_dockerfile.py
                    '''
                }
            }

            stage('Docker build (selective)') {
                when {
                    expression {
                        return !fileExists('.jenkins_skip_pipeline') || readFile('.jenkins_skip_pipeline').trim() != 'true'
                    }
                }
                steps {
                    sh '''
                        set -e
                        python3.11 scripts/ci_docker_build.py
                    '''
                }
            }

            stage('Compose up') {
                when {
                    expression {
                        return !fileExists('.jenkins_skip_pipeline') || readFile('.jenkins_skip_pipeline').trim() != 'true'
                    }
                }
                steps {
                    sh '''
                        set -e
                        . ./.jenkins_runtime.env
                        set -a
                        . ./.jenkins_build_plan.env
                        eval "$(python3.11 scripts/ci_compose_env.py)"
                        set +a
                        docker-compose up -d
                        docker-compose ps
                    '''
                }
            }

            stage('Verify stack') {
                when {
                    expression {
                        return !fileExists('.jenkins_skip_pipeline') || readFile('.jenkins_skip_pipeline').trim() != 'true'
                    }
                }
                steps {
                    sh '''
                        set -e
                        docker-compose ps
                    '''
                }
            }

            stage('Docker Hub push') {
                when {
                    expression {
                        return !fileExists('.jenkins_skip_pipeline') || readFile('.jenkins_skip_pipeline').trim() != 'true'
                    }
                }
                steps {
                    withCredentials([
                        usernamePassword(credentialsId: "${DOCKERHUB_CREDS_ID}", usernameVariable: 'DOCKERHUB_USERNAME', passwordVariable: 'DOCKERHUB_PASSWORD')
                    ]) {
                        sh '''
                            set -e
                            . ./.jenkins_runtime.env
                            . ./.jenkins_build_plan.env
                            echo "${DOCKERHUB_PASSWORD}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin
                            python3.11 scripts/ci_docker_push.py
                            docker logout || true
                        '''
                    }
                }
            }
        }

        post {
            success {
                script {
                    if (fileExists('.jenkins_skip_pipeline') && readFile('.jenkins_skip_pipeline').trim() == 'true') {
                        echo '=== SKIP: Stack entspricht bereits den erwarteten Tree-Tags. ==='
                    }
                }
            }
        }
    }
