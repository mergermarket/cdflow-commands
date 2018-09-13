// vim: filetype=groovy

def currentVersion
def nextVersion

def remote
def commit

def registry = "registry.hub.docker.com"

def githubCredentialsId = "github-credentials"

def dockerHubCredentialsId = 'dockerhub'
def imageName = 'mergermarket/cdflow-commands'

try {
    build(dockerHubCredentialsId, imageName, registry)

    publish(githubCredentialsId, dockerHubCredentialsId, imageName, registry)
}
catch (e) {
    currentBuild.result = 'FAILURE'
    notifySlack(currentBuild.result)
    throw e
}

def build(dockerHubCredentialsId, imageName, registry) {
    stage("Build") {
        node ("swarm2") {
            checkout scm
            currentVersion = sh(returnStdout: true, script: 'git describe --abbrev=0 --tags').trim().toInteger()
            remote = sh(returnStdout: true, script: "git config remote.origin.url").trim()
            commit = sh(returnStdout: true, script: "git rev-parse HEAD").trim()
            nextVersion = currentVersion + 1

            wrap([$class: "AnsiColorBuildWrapper"]) {
                sh "./test.sh"
            }

            def imageNameTag = "${imageName}:snapshot"
            docker.withRegistry("https://${registry}", dockerHubCredentialsId) {
                sh "docker image build -t ${imageNameTag} ."
                docker.image(imageNameTag).push()
            }

            build job: 'platform/cdflow-test-service-classic-metadata-handling', parameters: [string(name: 'CDFLOW_IMAGE_ID', value: imageNameTag) ]
        }
    }
}

def publish(githubCredentialsId, dockerHubCredentialsId, imageName, registry) {
    stage("Publish Release") {
        node ("swarm2") {
            withCredentials([[$class: 'UsernamePasswordMultiBinding', credentialsId: githubCredentialsId, usernameVariable: 'GIT_USERNAME', passwordVariable: 'GIT_PASSWORD']]) {
                git url: remote, commitId: commit, credentialsId: githubCredentialsId
                def author = sh(returnStdout: true, script: "git --no-pager show -s --format='%an' ${commit}").trim()
                def email = sh(returnStdout: true, script: "git --no-pager show -s --format='%ae' ${commit}").trim()
                sh """
                    git config user.name '${author}'
                    git config user.email '${email}'
                    git tag -a '${nextVersion}' -m 'Version ${nextVersion}'
                    git push 'https://${GIT_USERNAME}:${GIT_PASSWORD}@github.com/mergermarket/cdflow-commands' --tags
                """
            }

            docker.withRegistry("https://${registry}", dockerHubCredentialsId) {
                def app = docker.image "${registry}/${imageName}:snapshot"
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
