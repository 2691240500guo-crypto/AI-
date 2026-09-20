pipeline {
    agent any

    stages {

        stage('拉取代码') {
            steps {
                echo '========== 拉取 GitHub 代码 =========='
                sh 'pwd'
                sh 'ls -la'
            }
        }

        stage('检查构建环境') {
            steps {
                sh '''
                    echo "========== Python =========="
                    python3 --version

                    echo "========== Node.js =========="
                    node --version

                    echo "========== npm =========="
                    npm --version

                    echo "========== Docker =========="
                    docker --version
                '''
            }
        }

        stage('安装后端依赖') {
            steps {
                dir('智能健康测评/backend') {
                    sh '''
                        echo "========== 创建 Python 虚拟环境 =========="

                        rm -rf .jenkins-venv
                        python3 -m venv .jenkins-venv

                        echo "========== 升级 pip =========="
                        .jenkins-venv/bin/python -m pip install --upgrade pip

                        echo "========== 安装后端依赖 =========="
                        .jenkins-venv/bin/pip install -r requirements.txt
                    '''
                }
            }
        }

        stage('后端测试') {
            steps {
                dir('智能健康测评/backend') {
                    sh '''
                        echo "========== 执行 pytest =========="

                        .jenkins-venv/bin/python -m pytest -q
                    '''
                }
            }
        }

        stage('安装前端依赖') {
            steps {
                dir('智能健康测评/frontend') {
                    sh '''
                        echo "========== npm ci =========="

                        npm ci
                    '''
                }
            }
        }

        stage('构建前端') {
            steps {
                dir('智能健康测评/frontend') {
                    sh '''
                        echo "========== npm run build =========="

                        npm run build
                    '''
                }
            }
        }

        stage('CI 构建完成') {
            steps {
                echo '========================================'
                echo 'AI-talent CI 构建成功！'
                echo '后端依赖安装 + pytest + 前端构建全部完成'
                echo '========================================'
            }
        }
    }
}
