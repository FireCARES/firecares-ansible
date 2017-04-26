import click
import time
from tabulate import tabulate
from boto.cloudformation.connection import CloudFormationConnection
from boto.cloudformation.stack import Stack
from boto import connect_ec2
from boto.exception import BotoServerError, EC2ResponseError
from firecares_db import t as db_server_stack
from firecares_web import t as web_server_stack
from firecares_staging_db import t as db_staging_server_stack


def get_web_security_group(stack):
    """
    Filters stack outputs for the WebServerSecurityGroup key.
    """
    for output in stack.outputs:
        if output.key == 'WebServerSecurityGroup':
            return output


def delete_firecares_stack(stack_or_name):
    """
    Deletes the stack and un-registers entries in various security groups the app needs access to.
    """
    ec2 = connect_ec2()
    conn = CloudFormationConnection()

    if not isinstance(stack_or_name, Stack):
        stack_or_name = conn.describe_stacks(stack_name_or_id=stack_or_name)[0]

    old_sg = get_web_security_group(stack_or_name).value

    click.echo('Revoking access from security group {} to NFIRS.'.format(old_sg))
    ec2.revoke_security_group(group_id='sg-13fd9e77', src_security_group_group_id=old_sg, ip_protocol='tcp',
                              from_port=5432, to_port=5432)

    click.echo('Revoking access from security group {} to ELK.'.format(old_sg))
    ec2.revoke_security_group(group_id='sg-f1ce248e', src_security_group_group_id=old_sg, ip_protocol='tcp',
                              from_port=5043, to_port=5043)

    click.echo('Revoking access from security group {} to memcached'.format(old_sg))
    ec2.revoke_security_group(group_id='sg-8163f8e6', src_security_group_group_id=old_sg, ip_protocol='tcp',
                              from_port=11211, to_port=11211)

    click.echo('Deleting stack: {}'.format(stack_or_name.stack_name))
    conn.delete_stack(stack_or_name.stack_name)


@click.group(invoke_without_command=True)
@click.pass_context
def firecares_deploy(ctx):
    if ctx.invoked_subcommand is None:
        click.secho(r"""FireCARES Deployment Script""", fg='green')
        click.echo(firecares_deploy.get_help(ctx))
    return ctx.invoked_subcommand


@firecares_deploy.command()
@click.option('--ami', help='Currently deployed AMI')
@click.option('--keep', default=2, help='# of stacks to keep in AWS')
@click.option('--env', default='dev', help='Environment (dev/prod)')
def delete_old_stacks(ami, keep, env):
    """
    Delete old FireCARES webserver CloudFormation stacks from AWS.
    """
    _delete_old_stacks(ami, keep, env)


def _delete_old_stacks(ami=None, keep=2, env='dev'):
    conn = CloudFormationConnection()
    # If there are old stacks, flag them for deletion
    name = 'firecares-{}-web'.format(env)
    old_stacks = [n for n in conn.describe_stacks() if name in n.stack_name and (not ami or ami not in n.stack_name)]

    # Keep 2 stacks by default so that we don't have any potential downtime
    old_stacks = sorted(old_stacks, key=lambda x: x.creation_time, reverse=True)[keep:]
    click.secho("Deleting {count} stacks...".format(count=len(old_stacks)))
    for old_stack in old_stacks:
        click.secho("Deleting {}".format(old_stack.stack_name))
        delete_firecares_stack(old_stack)
    click.secho("Done")


@firecares_deploy.command()
@click.option('--ami', default='AMI', help='AMI to deploy')
@click.option('--env', default='dev', help='Environment')
@click.option('--commithash', help='The hash of the commit used to generate the AMI')
@click.option('--dbpass', help='Database password from firecares-db stack.')
@click.option('--dbuser', help='Database user from firecares-db stack.')
@click.option('--s3cors', default='*', help='S3 CORS allowed hosts')
def deploy(ami, env, commithash, dbpass, dbuser, s3cors):
    """
    Deploys a firecares environment.

    Note: This currently assumes the db stack is already created.
    """
    conn = CloudFormationConnection()
    ec2 = connect_ec2()

    db_stack = '-'.join(['firecares', env])
    key_name = '-'.join(['firecares', env])

    name = 'firecares-{}-web-{}'.format(env, commithash)

    try:
        stack = conn.describe_stacks(stack_name_or_id=name)[0]

    # The stack has not been created.
    except BotoServerError:
        conn.create_stack(stack_name=name,
                          template_body=web_server_stack.to_json(),
                          parameters=[
                              ('KeyName', key_name),
                              ('baseAmi', ami),
                              ('Environment', env),
                              ('CommitHash', commithash)])

        stack = conn.describe_stacks(stack_name_or_id=name)[0]

    while stack.stack_status == 'CREATE_IN_PROGRESS':
        click.secho('Stack creation in progress, waiting until the stack is available.')
        time.sleep(10)
        stack = conn.describe_stacks(stack_name_or_id=name)[0]

    if stack.stack_status != 'CREATE_COMPLETE':
        click.secho('Web stack creation failed...bailing')
        click.get_current_context().exit(code=1)

    db_stack = conn.describe_stacks(stack_name_or_id=db_stack)[0]

    if db_stack.stack_status != 'UPDATE_COMPLETE':
        click.secho('DB stack update failed...bailing')
        click.get_current_context().exit(code=2)

    sg = get_web_security_group(stack)

    if sg:
        click.secho('Updating database security group with ingress from new web security group.')

        db_params = [
            ('WebServerSG', sg.value),
            ('KeyName', 'firecares-{}'.format(env), True),
            ('Environment', env),
            ('S3StaticAllowedCORSOrigin', s3cors)]
        deploy_stack = db_staging_server_stack

        if env != 'prod':
            db_params.extend([('DBUser', dbuser, True), ('DBPassword', dbpass, True)])
            deploy_stack = db_server_stack

        try:
            conn.update_stack(db_stack.stack_name,
                              template_body=deploy_stack.to_json(),
                              parameters=db_params)
        except BotoServerError:
            click.secho('Stack already updated.')

        click.secho('Updating NFIRS database security group with ingress from new web security group.')
        try:
            ec2.authorize_security_group(group_id='sg-13fd9e77', src_security_group_group_id=sg.value, ip_protocol='tcp',
                                         from_port=5432, to_port=5432)
        except EC2ResponseError:
            click.secho('NFIRS web security group already exists.')

        click.secho('Updating ELK security group with ingress from new web security group.')
        try:
            ec2.authorize_security_group(group_id='sg-f1ce248e', src_security_group_group_id=sg.value, ip_protocol='tcp',
                                         from_port=5043, to_port=5043)
        except EC2ResponseError:
            click.secho('ELK web security group already exists.')

        click.secho('Updating memcached security group with ingress from new web security group.')
        try:
            ec2.authorize_security_group(group_id='sg-8163f8e6', src_security_group_group_id=sg.value, ip_protocol='tcp',
                                         from_port=11211, to_port=11211)
        except EC2ResponseError:
            click.secho('memcached web security group already exists.')

    _delete_old_stacks(ami=ami, env=env)


@firecares_deploy.command()
@click.option('--name', prompt='Enter the stack name.', confirmation_prompt=True)
def delete_stack(name):
    """
    Deletes the stack and un-registers entries in various security groups the app needs access to.
    """
    delete_firecares_stack(name)


@firecares_deploy.command()
def list_stacks():
    conn = CloudFormationConnection()

    def get_failures(stack):
        return ' | '.join(set([x.resource_status_reason for x in stack.describe_events()[:10] if x.resource_status.endswith('FAILED')]))

    rows = [[x.stack_name, x.stack_status, x.creation_time.isoformat(), get_failures(x)] for x in conn.describe_stacks() if x.stack_name.startswith('firecares')]
    click.secho(tabulate(rows, headers=['NAME', 'STATUS', 'CREATED AT', 'ERRORS']))


if __name__ == '__main__':
    firecares_deploy()
