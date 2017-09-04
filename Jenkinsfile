def slavePrefix = 'mmg'
def currentVersion
def nextVersion
def githubCredentialsId = "github-build-user"
def dockerHubCredentialsId = 'dockerhub'

def imageName = 'mergermarket/cdflow-commands'

try {
    build(slavePrefix, imageName)
    unitTest(slavePrefix)
    publishReleaseCandidate(slavePrefix, dockerHubCredentialsId, imageName)
    acceptanceTest(imageName)
    publishRelease(slavePrefix, githubCredentialsId, dockerHubCredentialsId, imageName)
}
catch (e) {
    currentBuild.result = 'FAILURE'
    notifySlack(currentBuild.result)
    throw e
}

def build(slavePrefix, imageName) {
    stage("Build") {
        node ("${slavePrefix}dev") {
            checkout scm
            currentVersion = sh(returnStdout: true, script: 'git describe --abbrev=0 --tags').trim().toInteger()
            nextVersion = currentVersion + 1
            wrap([$class: "AnsiColorBuildWrapper"]) {
                sh "docker build -t ${imageName}:${nextVersion} ."
            }
        }
    }
}

def unitTest(slavePrefix) {
    stage ("Unit Test") {
        node ("${slavePrefix}dev") {
          wrap([$class: "AnsiColorBuildWrapper"]) {
              sh "./test.sh"
          }
        }
    }
}

def publishReleaseCandidate(slavePrefix, dockerHubCredentialsId, imageName) {
    stage("Publish Release Candidate") {
        node ("${slavePrefix}dev") {
            withCredentials([[$class: "UsernamePasswordMultiBinding", credentialsId: dockerHubCredentialsId, passwordVariable: "DOCKER_HUB_PASSWORD", usernameVariable: "DOCKER_HUB_USERNAME"]]) {
                wrap([$class: "AnsiColorBuildWrapper"]) {
                    sh """
                      docker login -u \$DOCKER_HUB_USERNAME -p \$DOCKER_HUB_PASSWORD
                      docker push ${imageName}:${nextVersion}
                    """
                }
            }
        }
    }
}

def acceptanceTest(imageName) {
    stage ("Acceptance Test") {
      build job: 'platform/cdflow-test-service.temp', parameters: [string(name: 'CDFLOW_IMAGE_ID', value: "${imageName}:${nextVersion}") ]
    }
}

def publishRelease(slavePrefix, githubCredentialsId, dockerHubCredentialsId, imageName) {
    stage("Publish Release") {
        node ("${slavePrefix}dev") {

            sshagent(githubCredentialsId) {
                sh """
                  git tag -a '${nextVersion}' -m 'Version ${nextVersion}'
                  git push --tags
                """
            }

            withCredentials([[$class: "UsernamePasswordMultiBinding", credentialsId: dockerHubCredentialsId, passwordVariable: "DOCKER_HUB_PASSWORD", usernameVariable: "DOCKER_HUB_USERNAME"]]) {
                wrap([$class: "AnsiColorBuildWrapper"]) {
                    sh """
                      docker login -u \$DOCKER_HUB_USERNAME -p \$DOCKER_HUB_PASSWORD
                      docker pull ${imageName}:${nextVersion}
                      docker tag ${imageName}:${nextVersion} ${imageName}:latest
                      docker push ${imageName}:latest
                    """
                }
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
