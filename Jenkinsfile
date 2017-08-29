def slavePrefix = "mmg"

try {
    build()
    unitTest(slavePrefix)
    // publish(releaseCandidate = true)
    // acceptanceTest()
    // publish()
}
catch (e) {
    currentBuild.result = 'FAILURE'
    notifySlack(currentBuild.result)
    throw e
}

def build(slavePrefix) {
    stage("Build") {
        node ("${slavePrefix}dev") {
            def commitObject = checkout scm
            sh "docker build -t mergermarket/cdflow-commands:${commitObject.GIT_COMMIT} ."
        }
    }
}

def unitTest(slavePrefix) {
    stage ("Unit Test") {
        node ("${slavePrefix}dev") {
            sh "./test.sh"
        }
    }
}

def publish(releaseCandidate = false) {

}

def acceptanceTest() {
    stage ("Acceptance Test") {
      build job: 'platform/cdflow-test-service.temp', parameters: [string(name: 'CDFLOW_IMAGE_ID', value: "${GIT_COMMIT}") ]
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
