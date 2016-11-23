"""
Deploy to MMG ECS infrastructure

Usage:
    infra/deploy <environment> <version> [-c <component-name>] [-l <leg>] [-p] [-- <tfargs>...]

Options:
    # Override component name (default from repo name)
    -c <component-name>, --component-name <component-name>
    # Set a leg postfix for the service name
    -l <leg>, --leg <leg>
    # Only run terraform plan, not apply
    -p, --plan
"""

from __future__ import print_function
from docopt import docopt
from subprocess import check_call, check_output

import hashlib
import logging
import util
import os
import sys
import shutil
import pdb
import json
from tempfile import NamedTemporaryFile


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_nested_key(data, keys, default=None):
    """
    Takes a nested dict and array of keys and returns the corresponding value, or the passed
    in default (default None) if it does not exist.
    """
    if keys[0] not in data:
        return default
    elif len(data) == 1:
        return data[keys[0]]
    else:
        return get_nested_key(data[keys[0]], keys[1:], default)


class Deployment:

    """
    Manages the process of deployment.
    """

    def __init__(self, argv, environ, shell_runner=None, service_json_loader=None, platform_config_loader=None):
        arguments = docopt(__doc__, argv=argv)
        self.shell_runner = shell_runner if shell_runner is not None else util.ShellRunner()
        self.environment = arguments.get('<environment>')
        self.version = arguments.get('<version>')
        self.component_name = util.get_component_name(arguments, environ, self.shell_runner)
        self.leg = arguments.get('--leg')
        self.plan = arguments.get('--plan')
        self.tfargs = arguments.get('<tfargs>')

        if not service_json_loader:
            service_json_loader = util.ServiceJsonLoader()
        self.config = None
        self.metadata = util.apply_metadata_defaults(
            service_json_loader.load(),
            self.component_name
        )
        if not platform_config_loader:
            platform_config_loader = util.PlatformConfigLoader()
        self.account_id = platform_config_loader.load(self.metadata['REGION'], self.metadata['ACCOUNT_PREFIX'], self.prod())['account_id']
        if self.prod():
            dev_account_id = platform_config_loader.load(self.metadata['REGION'], self.metadata['ACCOUNT_PREFIX'])['account_id']
        else:
            dev_account_id = self.account_id
        self.ecr_image_name = util.ecr_image_name(
            dev_account_id,
            self.metadata['REGION'],
            self.component_name,
            self.version
        )
        self.aws = None

    def run(self):
        """
        Run the deployment.
        """
        print('deploying %s version %s to %s' %
              (self.component_name, self.version, self.environment))

        # perform a cleanup, in case any residue from past runs is still around
        self.cleanup()

        # initialise Boto Session
        self.get_aws()

        # construct local env
        env = os.environ.copy()
        (aws_access_key, aws_secret_key, aws_session_token) = self._get_aws_credentials(self.aws)
        env['AWS_ACCESS_KEY_ID'] = aws_access_key
        env['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
        env['AWS_SESSION_TOKEN'] = aws_session_token
        env['AWS_DEFAULT_REGION'] = self.metadata['REGION']

        print("Preparing S3 bucket for terragrunt...")
        s3_bucket_name = self.terragrunt_s3_bucket_name()
        self.s3_bucket_prep(s3_bucket_name)

        print("Generating terragrunt config...")
        self.generate_terragrunt_config(self.metadata['REGION'], s3_bucket_name, self.environment,
                                        self.component_name)

        # get all the relevant modules
        check_call("terraform get infra", env=env, shell=True)

        # process secrets
        secrets_file = 'config/secrets.json'
        if self._secrets(secrets_file):
            secrets = self._read_secrets(secrets_file)
            decrypted_secrets_file = self._generate_decrypted_credentials(secrets, self.metadata["TEAM"], self.component_name, self.environment, env)
        else:
            decrypted_secrets_file = None

        self.terragrunt('plan', self.environment, self.ecr_image_name, self.component_name, self.metadata['REGION'],
                        self.metadata['TEAM'], self.version, decrypted_secrets_file, env)
        if self.plan is False:
            self.terragrunt('apply', self.environment, self.ecr_image_name, self.component_name, self.metadata['REGION'],
                            self.metadata['TEAM'], self.version, decrypted_secrets_file, env)

        # clean up all irrelevant files
        self.cleanup()

    def _secrets(self, file):
        """
        Helper method to check whether we need to process secrets or not

        Params:
            file: file location to check whether it exist
        Returns:
            bool: True is it exist, False if not
        """

        if os.path.exists(file):
            return True
        else:
            return False

    def _read_secrets(self, file):
        """
        Reads given file and decodes it to python dict

        Params:
            file: location to file holding json payload
        Returns:
            dict: Python dict of data loaded from the input json file
        """
        with open(file) as data_file:
            data = json.load(data_file)

            return data

    def _credstash_get(self, key, team, component, environment, exec_env):
        """
        Calls out to credstash and gets given key

        Params:
            key: key to fetch using credstash
            team: team; used to differentiate which KMS master key to use
            component: used for context
            environment: used for context
            exec_env: used by subprocess call

        Returns:
            string: result credstash got back the "vault"
        """
        try:
            s = check_output(["credstash", "-t", "credstash-%s" % team,
                                           "get",
                                           "-n",
                                           key,
                                           "component=%s" % component,
                                           "env=%s" % environment], env=exec_env)
        except:
            print("Error while trying to fetch/decrypt value for {} secret...".format(key))
            s = "NOTFOUND"

        return s

    def _generate_decrypted_credentials(self, secrets, team, component, env, exec_env):
        """
        Params:
            secrets: a dictionary of secrets to get value for
            team: needed by _credstash_get
            component: needed by _credstash_get
            env: needed by _credstash_get
            exec_env: needed by _credstash_get
        Returns:
            file: file-location with the resulting json
        """
        decrypted_secrets = {}

        for key in secrets["secrets"]:
            decrypted_val = self._credstash_get(key, team, component, env, exec_env)
            decrypted_secrets[key] = decrypted_val

        f = NamedTemporaryFile(delete=False)
        f.write(json.dumps({"secrets": decrypted_secrets}))
        return f.name

    def get_aws(self):
        """
        Gets an AWS session.
        """
        if self.aws is None:
            self.aws = util.assume_role(self.metadata['REGION'], self.account_id)
        return self.aws

    def _get_aws_credentials(self, session):
        """
        Gets temporary AWS credentials based on the passed boto3.session.Session

        Params:
            boto3.session.Session: Boto3 session to get the credentials against

        Returns:
            array: [access_key, secret_key]
        """
        try:
            aws_access_key = session.get_credentials().access_key
            aws_secret_key = session.get_credentials().secret_key
            aws_session_token = session.get_credentials().token
        except:
            logger.error("Exception caught while trying to get temporary AWS credentials!")

        return (aws_access_key, aws_secret_key, aws_session_token)

    def set_aws(self, aws):
        """
        Sets an AWS session - used to inject dependency in tests.
        """
        self.aws = aws

    def terragrunt_s3_bucket_name(self):
        """Generates S3 bucket name Terragrunt will use based on account
        ID.

        Takes the ID and hashes it to make it smaller (6 characters)

        Returns:
            string: The return value.  Non-empty for success

        """
        return "terraform-tfstate-%s" % hashlib.md5(self.account_id.encode('utf-8')).hexdigest()[:6]

    def s3_bucket_prep(self, s3_bucket_name):
        """Checks whether given S3 Bucket exists and if not, it creates
        it

        Arguments:
            s3_bucket_name - name of the bucket (string)

        Returns:
            bool: True if successful; False otherwise
        """
        s3 = self.aws.resource('s3')

        if not s3.Bucket(s3_bucket_name) in s3.buckets.all():
            logger.info("Bucket %s doesn't exist... Trying to create...", s3_bucket_name)
            try:
                s3.create_bucket(Bucket=s3_bucket_name,
                                 CreateBucketConfiguration={'LocationConstraint': self.region})
            except Exception as e:
                logger.exception("Error while trying to create bucket %s (%s)",
                                 s3_bucket_name, str(e))

    def generate_terragrunt_config(self, region, s3_bucket_name, environment, component_name):
        """Generates terragrunt config as per terragrunt documentation"""
        state_file_id = "{env}-{component}".format(env=environment, component=component_name)

        grunt_config_template = """lock = {{
  backend = "dynamodb"
  config {{
    state_file_id = "{state_file_id}"
    aws_region = "{region}"
    table_name = "terragrunt_locks"
    max_lock_retries = 360
  }}
}}
remote_state = {{
  backend = "s3"
  config {{
    encrypt = "true"
    bucket = "{s3_bucket}"
    key = "{env}/{component}/terraform.tfstate"
    region = "{region}"
  }}
}}"""

        with open('.terragrunt', 'w') as f:
            f.write(grunt_config_template.format(
                state_file_id=state_file_id,
                region=region,
                s3_bucket=s3_bucket_name,
                env=environment,
                component=component_name
            ))

    def terragrunt(self, action, environment, image, component, region, team, version, secrets, exec_env):
        """
        Runs terragrunt.
        """
        configfile = "config/%s.json" % environment
        if os.path.exists(configfile):
            environmentconfig = [ "-var-file", configfile ]
        else:
            environmentconfig = []

        # include secrets if they're present
        if secrets is not None:
            secretsconfig = ["-var-file", secrets]
        else:
            secretsconfig = []

        check_call([
            "terragrunt", action, "-var", "component=%s" % component,
            "-var", "env=%s" % environment,
            "-var", "image=%s" % image,
            "-var", "team=%s" % team,
            ] + self.tfargs + [
            "-var", 'version="%s"' % version,
            "-var-file", util.platform_config_filename(region, self.metadata['ACCOUNT_PREFIX'], self.prod()),
            ] + environmentconfig + secretsconfig + [
            "infra"
        ], env=exec_env)

        return True

    def cleanup(self):
        # clean up after terraform run
        try:
            shutil.rmtree(".terraform")
            os.remove(".terragrunt")
        except:
            pass

    def prod(self):
        """
        Returns True if the prod account should be used.
        """
        return self.environment == 'live' or self.environment == 'debug' or self.environment == 'prod'


def main():
    """
    Entry-point for script.
    """
    try:
        deployment = Deployment(sys.argv[1:], os.environ)
        deployment.run()
    except util.UserError as err:
        print('error: %s' % str(err), file=sys.stderr)
        sys.stderr.flush()
        exit(1)


if __name__ == '__main__':
    main()
