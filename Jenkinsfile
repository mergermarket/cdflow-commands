def slavePrefix = "mmg"
def commitObject
def dockerHubCredentialsId = "dockerhub"

try {
    build(slavePrefix)
    unitTest(slavePrefix)
    publishReleaseCandidate(slavePrefix, dockerHubCredentialsId)
    acceptanceTest()
    publishRelease(slavePrefix, dockerHubCredentialsId)
}
catch (e) {
    currentBuild.result = 'FAILURE'
    notifySlack(currentBuild.result)
    throw e
}

def build(slavePrefix) {
    stage("Build") {
        node ("${slavePrefix}dev") {
            commitObject = checkout scm
            wrap([$class: "AnsiColorBuildWrapper"]) {
                sh "docker build -t mergermarket/cdflow-commands:${commitObject.GIT_COMMIT} ."
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

def publishReleaseCandidate(slavePrefix, dockerHubCredentialsId) {
    stage("Publish Release Candidate") {
        node ("${slavePrefix}dev") {
            withCredentials([[$class: "UsernamePasswordMultiBinding", credentialsId: dockerHubCredentialsId, passwordVariable: "DOCKER_HUB_PASSWORD", usernameVariable: "DOCKER_HUB_USERNAME"]]) {
                wrap([$class: "AnsiColorBuildWrapper"]) {
                    sh '''
                      docker login -u $DOCKER_HUB_USERNAME -p $DOCKER_HUB_PASSWORD
                      docker push mergermarket/cdflow-commands:${commitObject.GIT_COMMIT}
                    '''
                }
            }
        }
    }
}

def acceptanceTest() {
    stage ("Acceptance Test") {
      build job: 'platform/cdflow-test-service.temp', parameters: [string(name: 'CDFLOW_IMAGE_ID', value: "mergermarket/cdflow-commands:${commitObject.GIT_COMMIT}") ]
    }
}

def publishRelease(slavePrefix, dockerHubCredentialsId) {
    stage("Publish Release") {
        node ("${slavePrefix}dev") {
            withCredentials([[$class: "UsernamePasswordMultiBinding", credentialsId: dockerHubCredentialsId, passwordVariable: "DOCKER_HUB_PASSWORD", usernameVariable: "DOCKER_HUB_USERNAME"]]) {
                wrap([$class: "AnsiColorBuildWrapper"]) {
                    sh '''
                      docker login -u $DOCKER_HUB_USERNAME -p $DOCKER_HUB_PASSWORD
                      docker tag mergermarket/cdflow-commands:latest
                      docker push mergermarket/cdflow-commands:latest
                    '''
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
