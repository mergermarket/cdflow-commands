def slavePrefix = 'mmg'

def currentVersion
def nextVersion
def commit

//  docker
def dockerHubCredentialsId = 'dockerhub'
def imageName = 'mergermarket/cdflow-commands'

try {
    build(slavePrefix, dockerHubCredentialsId, imageName)
    // test(slavePrefix, imageName)
    publish(slavePrefix, dockerHubCredentialsId, imageName)
}
catch (e) {
    currentBuild.result = 'FAILURE'
    notifySlack(currentBuild.result)
    throw e
}

def build(slavePrefix, dockerHubCredentialsId, imageName) {
    stage("Build") {
        node ("${slavePrefix}dev") {
            checkout scm
            currentVersion = sh(returnStdout: true, script: 'git describe --abbrev=0 --tags').trim().toInteger()
            commit = sh(returnStdout: true, script: "git rev-parse HEAD").trim()
            nextVersion = currentVersion + 1

            docker.withRegistry('https://registry.hub.docker.com', dockerHubCredentialsId) {
                docker.build("${imageName}:snapshot").push()
            }
        }
    }
}

def unitTest(slavePrefix, imageName) {
    stage ("Unit Test") {
        node ("${slavePrefix}dev") {
          wrap([$class: "AnsiColorBuildWrapper"]) {
              sh "./test.sh"
          }
        }
    }

    stage ("Acceptance Test") {
        build job: 'platform/cdflow-test-service.temp', parameters: [string(name: 'CDFLOW_IMAGE_ID', value: "${imageName}:snapshot") ]
    }
}

def publish(slavePrefix, dockerHubCredentialsId, imageName) {
    stage("Publish Release") {
        node ("${slavePrefix}dev") {
            checkout scm
            def author = sh(returnStdout: true, script: "git --no-pager show -s --format='%an' ${commit}").trim()
            def email = sh(returnStdout: true, script: "git --no-pager show -s --format='%ae' ${commit}").trim()
            sh """
                git checkout -q ${commit}
                git config user.name '${author}'
                git config user.email '${email}'
                git tag -a '${nextVersion}' -m 'Version ${nextVersion}'
                git push --tags
            """

            docker.withRegistry('https://registry.hub.docker.com', dockerHubCredentialsId) {
                def app = docker.image "${imageName}:snapshot"
                app.pull()
                app.push "${nextVersion}"
                app.push 'latest'
            }
        }
    }
}

def notifySlack(String buildStatus = 'STARTED') {
    // Build status of null means success.
    buildStatus = buildStatus ?: 'SUCCESS'

    def color

    if (buildStatus == 'STARTED') {
        color = '#D4DADF'
    } else if (buildStatus == 'SUCCESS') {
        color = '#BDFFC3'
    } else if (buildStatus == 'UNSTABLE') {
        color = '#FFFE89'
    } else {
        color = '#FF9FA1'
    }

    def msg = "${buildStatus}: `${env.JOB_NAME}` #${env.BUILD_NUMBER}:\n${env.BUILD_URL}"
    slackSend(color: color, message: msg, channel: '#platform-team-alerts', token: fetch_credential('slack-r2d2'))
}

def fetch_credential(name) {
  def v;
  withCredentials([[$class: 'StringBinding', credentialsId: name, variable: 'CREDENTIAL']]) {
      v = env.CREDENTIAL;
  }
  return v
}
