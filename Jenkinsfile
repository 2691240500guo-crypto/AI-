pipeline {
    agent any

    stages {

        stage('拉取代码') {
            steps {
                echo 'GitHub 代码已经成功拉取'
                sh 'pwd'
                sh 'ls -la'
            }
        }

        stage('检查项目结构') {
            steps {
                sh '''
                    echo "===== 项目目录 ====="
                    ls -la "智能健康测评"

                    echo "===== Python ====="
                    python3 --version || true

                    echo "===== Node.js ====="
                    node --version || true

                    echo "===== npm ====="
                    npm --version || true

                    echo "===== Docker ====="
                    docker --version || true
                '''
            }
        }

        stage('进入项目目录') {
            steps {
                dir('智能健康测评') {
                    sh '''
                        echo "===== 当前项目目录 ====="
                        pwd

                        echo "===== 项目文件 ====="
                        ls -la
                    '''
                }
            }
        }
    }
}
