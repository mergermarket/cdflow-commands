// variables

def remote
def commit
def shortCommit
def version

// configuration

def slavePrefix = "mmg"
def awsCredentialsId = "platform-mergermarket"


// constants

def githubCredentialsId = "github-build-user"


// pipeline definition
test(awsCredentialsId, slavePrefix)

//release(awsCredentialsId, slavePrefix)

//deploy("aslive", slavePrefix, githubCredentialsId, awsCredentialsId)

//deploy("live", slavePrefix, githubCredentialsId, awsCredentialsId)

// reusable code

// perform a release - note release() must be called before calling deploy()
def test(awsCredentialsId, slavePrefix) {
    stage ("Test") {
        node ("${slavePrefix}dev") {

            checkout scm
            sh "./test.sh"
        }
    }
}

def release(awsCredentialsId, slavePrefix) {
    stage ("Release") {
        node ("${slavePrefix}dev") {

            checkout scm

            remote = sh(returnStdout: true, script: "git config remote.origin.url").trim()
            commit = sh(returnStdout: true, script: "git rev-parse HEAD").trim()
            shortCommit = sh(returnStdout: true, script: "git rev-parse --short HEAD").trim()
            version = "${env.BUILD_NUMBER}-${shortCommit}"

            withCredentials([[$class: "UsernamePasswordMultiBinding", credentialsId: awsCredentialsId, passwordVariable: "AWS_SECRET_ACCESS_KEY", usernameVariable: "AWS_ACCESS_KEY_ID"]]) {
                wrap([$class: "AnsiColorBuildWrapper"]) {
                    sh "./infra/scripts/release ${version}"
                }
            }
        }
    }
}

// perform a deploy
def deploy(env, slavePrefix, githubCredentialsId, awsCredentialsId) {
    
    account = env == "live" || env == "debug" ? "prod" : "dev"

    stage ("Deploy to ${env}") {
        node ("${slavePrefix}${account}") {
            // work around "checkout scm" getting the wrong commit when stages from different commits are interleaved
            git url: remote, credentialsId: githubCredentialsId
            sh "git checkout -q ${commit}"

            withCredentials([[$class: "UsernamePasswordMultiBinding", credentialsId: awsCredentialsId, passwordVariable: "AWS_SECRET_ACCESS_KEY", usernameVariable: "AWS_ACCESS_KEY_ID"]]) {
                wrap([$class: "AnsiColorBuildWrapper"]) {
                    sh "./infra/scripts/deploy ${env} ${version}"
                }
            }
        }
    }
}

