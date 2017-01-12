"""
Deploy to MMG ECS infrastructure.

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
from subprocess import check_call

import hashlib
import logging
import util
import os
import sys
import shutil
import json
import time
import re

logging.basicConfig(format='[%(asctime)s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def get_nested_key(data, keys, default=None):
    """
    Take a nested dict and array of keys and returns the corresponding value.

    (or the passedin default (default None) if it does not exist.
    """
    if keys[0] not in data:
        return default
    elif len(data) == 1:
        return data[keys[0]]
    else:
        return get_nested_key(data[keys[0]], keys[1:], default)


class Deployment:
    """Manage the process of deployment."""

    def __init__(self, argv, environ, shell_runner=None, service_json_loader=None, platform_config_loader=None):
        """Deployment constructor."""
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
        self.account_id = platform_config_loader.load(self.metadata['REGION'], self.metadata['ACCOUNT_PREFIX'],
                                                      util.prod(self.environment))['account_id']
        if util.prod(self.environment):
            dev_account_id = platform_config_loader.load(self.metadata['REGION'],
                                                         self.metadata['ACCOUNT_PREFIX'])['account_id']
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
        """Run the deployment."""
        deploy_start_time = time.time()
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

        # initialise Terragrunt
        terragrunt = util.Terragrunt(self.metadata, self.environment, self.component_name, self.ecr_image_name,
                                     self.version, self.terragrunt_s3_bucket_name(), env)

        # process secrets
        if "CREDSTASH" in self.metadata:
            secrets = util.Credstash().process(self.metadata["CREDSTASH"], self.metadata['TEAM'],
                                               self.component_name, self.environment, env)
        else:
            secrets = None

        # get all the relevant modules
        check_call("terraform get infra", env=env, shell=True)

        terragrunt.run('plan', secrets, self.tfargs)
        if self.plan is False:
            terragrunt.run('apply', secrets, self.tfargs)

        # parse / process terraform output; this is needed to monitor deploy progress
        (ecs_cluster_name, ecs_service_arn, ecs_service_task_definition_arn) = self.parse_terraform_output(json.loads(terragrunt.output()))
        monitor_deploy = self.monitor_deploy(ecs_cluster_name, ecs_service_arn, ecs_service_task_definition_arn)
        if monitor_deploy:
            self.monitor_deploy_progress(self.aws.client('ecs'), self.aws.client('elbv2'), ecs_cluster_name, ecs_service_arn,
                                         ecs_service_task_definition_arn, deploy_start_time)

        # once finished, establish time taken to complete
        deploy_time = time.strftime("%Mm%Ss", time.gmtime(time.time() - deploy_start_time))
        logger.info("Deploy finished in {}".format(deploy_time))

        # clean up
        self.cleanup()

    def monitor_deploy_progress(self, ecs, elbv2, ecs_cluster_name, ecs_service_arn, ecs_service_task_definition_arn, deploy_start_time):
        """Monitor deploy progress and fail if required"""
        # set deploy flags to start state
        deploy_finished = False
        ecs_service_update_finished = False
        elbv2_deploy_finished = False
        deploy_success_count = 0
        deploy_failed_healthcheck = 0

        # deploy monitoring
        # TODO: consolidate this piece of functionality into a separate method?
        while deploy_finished is not True:
            services = ecs.describe_services(cluster=ecs_cluster_name, services=[ecs_service_arn])

            # check whether service update has already finished
            if self.get_service_update_progress(ecs_service_task_definition_arn, services) and not ecs_service_update_finished:
                logger.info("ECS service update has been finished...")
                ecs_service_update_finished = True
            elif not ecs_service_update_finished:
                logger.info("ECS service update still in progress...")

            # if ECS service has been updated, start checking target group targets healthiness
            if ecs_service_update_finished and not elbv2_deploy_finished:
                tasks_list_running = ecs.list_tasks(cluster=ecs_cluster_name, serviceName=ecs_service_arn)
                if len(tasks_list_running['taskArns']) > 0:
                    ecs_tasks_running = ecs.describe_tasks(cluster=ecs_cluster_name, tasks=tasks_list_running['taskArns'])
                else:
                    ecs_tasks_running = {'tasks': []}

                tasks_list_stopped = ecs.list_tasks(cluster=ecs_cluster_name, serviceName=ecs_service_arn, desiredStatus='STOPPED')
                if len(tasks_list_stopped['taskArns']) > 0:
                    ecs_tasks_stopped = ecs.describe_tasks(cluster=ecs_cluster_name, tasks=tasks_list_stopped['taskArns'])
                else:
                    ecs_tasks_stopped = {'tasks': []}

                tasks = ecs_tasks_running['tasks'] + ecs_tasks_stopped['tasks']

                elb_st = self.get_elbv2_deploy_progress(ecs_service_task_definition_arn, services,
                                                        tasks, ecs_cluster_name, ecs, elbv2)

                # if number of healthy instances running off the new taskDef is equal to desiredCount
                # of running containers, wait 5 cycles and finish deploy
                if elb_st[0] == services['services'][0]['desiredCount']:
                    deploy_success_count += 1
                if deploy_success_count > 5:
                    elbv2_deploy_finished = True

                # see if we've any unhealthy instances, if so increment marker for them; if it reaches
                # 2 - fail the deploy due to tasks failing healthcheck
                if elb_st[3] > 0:
                    deploy_failed_healthcheck += 1
                if deploy_failed_healthcheck == 2:
                    raise Exception("Deploy failed!  New containers are failing the load-balancer healthcheck!")

            # if all deploy steps have finished, finish deploy
            if ecs_service_update_finished and elbv2_deploy_finished:
                deploy_finished = True

            # check whether deploy hasn't timed out
            if self.deploy_timed_out(deploy_start_time):
                raise Exception("Deploy has timed out... Time limit of {} has been reached. Please investigate the cause of this!".format(600))

            time.sleep(15)

    def deploy_timed_out(self, start_time, limit=600):
        """Return True/False depending whether time limit has been hit."""
        if time.time() - start_time > limit:
            return True
        else:
            return False

    def monitor_deploy(self, par1, par2, par3):
        """Decide whether deploy should be monitored.

        Base decision on the three parameters passed; if any of the is
        None, return False; otherwise return True
        """
        if par1 is None or par2 is None or par3 is None:
            return False
        else:
            return True

    def parse_terraform_output(self, output):
        """Prase and return Terraform output."""
        ecs_cluster_name = util.terraform_output_filter('ecs_cluster_name', output)
        ecs_service_arn = util.terraform_output_filter('ecs_service_arn', output)
        ecs_service_task_definition_arn = util.terraform_output_filter('ecs_service_task_definition_arn', output)

        return str(ecs_cluster_name), str(ecs_service_arn), str(ecs_service_task_definition_arn)

    def get_elbv2_deploy_progress(self, task_def_arn, services, tasks, ecs_cluster_name, ecs, elbv2):
        """Track ELBv2 deploy status.

        Returns:
            list: list of int of healthy, initial, draining, unhealthy instances of specific task_arn
        """
        ecs_container_instances = [task['containerInstanceArn'] for task in tasks]
        ecs_container_instances = list(set(ecs_container_instances))  # get only unique instance-ids
        describe_target_health = elbv2.describe_target_health(TargetGroupArn=services['services'][0]['loadBalancers'][0]['targetGroupArn'])

        elbv2_health = {}
        container_instances = ecs.describe_container_instances(cluster=ecs_cluster_name, containerInstances=ecs_container_instances)
        for target in describe_target_health['TargetHealthDescriptions']:
            (ecs_instance, port, state) = self.get_ecs_instance_metadata(target, container_instances)
            task_arn = self.get_task_arn(ecs_instance, port, tasks)

            if task_arn is not None:
                if task_arn not in elbv2_health:
                    elbv2_health[task_arn] = {
                        'healthy': 0,
                        'initial': 0,
                        'draining': 0,
                        'unhealthy': 0
                    }

                p = elbv2_health[task_arn][target['TargetHealth']['State']]
                elbv2_health[task_arn][target['TargetHealth']['State']] = p + 1

        for task in elbv2_health:
            logger.info("ELB status for {task}  healthy:{h}  initial:{i}  draining:{d}  unhealthy:{u}".format(
                        task=self.get_ecs_task_from_arn(task),
                        h=elbv2_health[task]['healthy'],
                        i=elbv2_health[task]['initial'],
                        d=elbv2_health[task]['draining'],
                        u=elbv2_health[task]['unhealthy']))

        if task_def_arn in elbv2_health:
            if 'healthy' in elbv2_health[task_def_arn]:
                return [elbv2_health[task_def_arn]['healthy'], elbv2_health[task_def_arn]['initial'],
                       elbv2_health[task_def_arn]['draining'], elbv2_health[task_def_arn]['unhealthy']]
            else:
                return [0, 0, 0, 0]
        else:
            return [0, 0, 0, 0]

    def get_ecs_task_from_arn(self, arn):
        """Return ECS task fragment from given arn."""
        return re.search(r'^arn:aws:ecs:.*:[0-9]{12}:task-definition\/(.*)', arn).group(1)

    def get_service_update_progress(self, ecs_service_task_definition_arn, describe_services):
        """Check progress of service update.  Return True if succeeded."""
        for deployment in describe_services['services'][0]['deployments']:
            if deployment['taskDefinition'] == ecs_service_task_definition_arn and deployment['status'] == 'PRIMARY':
                return True
        else:
            return False

    def get_task_arn(self, container_instance, port, service_tasks):
        """Get task ARN based from a combination of container instance and port."""
        task_definition_arn = None
        for i in service_tasks:
            if 'networkBindings' in i['containers'][0]:
                host_port = i['containers'][0]['networkBindings'][0]['hostPort']
            else:
                host_port = 0

            if (i['containerInstanceArn'] == container_instance and host_port == port):
                task_definition_arn = i['taskDefinitionArn']

        if task_definition_arn == None:
            return None
        else:
            return task_definition_arn

    def get_ecs_instance_metadata(self, target, describe_container_instances):
        """Return ECS instance metadata including ECS instance ARN.

        This is needed as boto3.elbv2.describe_target_health returns instance
        id in EC2 form (i-xxxxxx) and we need it as ECS instance ARN so we can
        later use it to find what specific container does it refer to.

        Params:
            target (dict) - a single element from boto3.elbv2.describe_target_health
            describe_container_instances (array) - result of boto3.ecs.describe_container_instances
        Returns:
            array - ECS container instance ARN, port, state (healthy, draining etc.)
        """
        container_instance = None
        for i in describe_container_instances['containerInstances']:
            if i['ec2InstanceId'] == target['Target']['Id']:
                container_instance = i['containerInstanceArn']

        state = target['TargetHealth']['State']
        port = target['Target']['Port']
        return container_instance, port, state

    def get_deployment(self, deployments, status, key):
        """Return relevant key from deployments dictionary, based on status."""
        for d in deployments:
            if 'status' in d:
                if d['status'] == status:
                    return d[key]
            else:
                return None

    def get_aws(self):
        """Get an AWS session."""
        if self.aws is None:
            self.aws = util.assume_role(self.metadata['REGION'], self.account_id)
        return self.aws

    def _get_aws_credentials(self, session):
        """
        Get temporary AWS credentials based on the passed boto3.session.Session.

        Params:
            boto3.session.Session: Boto3 session to get the credentials against

        Returns:
            array: [access_key, secret_key]
        """
        try:
            aws_access_key = session.get_credentials().access_key
            aws_secret_key = session.get_credentials().secret_key
            aws_session_token = session.get_credentials().token
        except Exception as e:
            logger.error("Exception caught while trying to get temporary AWS credentials: " + str(e))
            raise

        return aws_access_key, aws_secret_key, aws_session_token

    def set_aws(self, aws):
        """Set an AWS session - used to inject dependency in tests."""
        self.aws = aws

    def terragrunt_s3_bucket_name(self):
        """Generate S3 bucket name Terragrunt will use based on account ID.

        Takes the ID and hashes it to make it smaller (6 characters)

        Returns:
            string: The return value.  Non-empty for success

        """
        return "terraform-tfstate-%s" % hashlib.md5(self.account_id.encode('utf-8')).hexdigest()[:6]

    def cleanup(self):
        """Clean up after terraform run."""
        try:
            shutil.rmtree(".terraform")
            os.remove(".terragrunt")
        except:
            pass


def main():
    """Entry-point for script."""
    try:
        deployment = Deployment(sys.argv[1:], os.environ)
        deployment.run()
    except util.UserError as err:
        print('error: %s' % str(err), file=sys.stderr)
        sys.stderr.flush()
        exit(1)


if __name__ == '__main__':
    main()
