import click
import time
from boto.cloudformation.connection import CloudFormationConnection
from boto.cloudformation.stack import Stack
from boto import connect_ec2
from boto.exception import BotoServerError
from firecares_db import t as db_server_stack
from firecares_web import t as web_server_stack


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
@click.option('--ami', default='AMI', help='AMI to deploy')
@click.option('--env', default='dev', help='Environment')
@click.option('--dbpass', help='Database password from firecares-db stack.')
@click.option('--dbuser', help='Database user from firecares-db stack.')
def deploy(ami, env, dbpass, dbuser):
    """
    Deploys a firecares environment.

    Note: This currently assumes the db stack is already created.
    """
    conn = CloudFormationConnection()
    ec2 = connect_ec2()

    db_stack = '-'.join(['firecares', env])
    key_name = '-'.join(['firecares', env])

    name = 'firecares-dev-web-{}'.format(ami)
    try:
        stack = conn.describe_stacks(stack_name_or_id=name)[0]

    # The stack has not been created.
    except BotoServerError:
        conn.create_stack(stack_name=name,
                          template_body=web_server_stack.to_json(),
                          parameters=[
                              ('KeyName', key_name),
                              ('baseAmi', ami)])

        stack = conn.describe_stacks(stack_name_or_id=name)[0]

        while stack.stack_status == 'CREATE_IN_PROGRESS':
            click.secho('Stack creation in progress, waiting until the stack is available.')
            time.sleep(10)
            stack = conn.describe_stacks(stack_name_or_id=name)[0]

    db_stack = conn.describe_stacks(stack_name_or_id=db_stack)[0]

    sg = get_web_security_group(stack)

    if sg:
        click.secho('Updating database security group with ingress from new web security group.')
        conn.update_stack(db_stack.stack_name,
                          template_body=db_server_stack.to_json(),
                          parameters=[
                              ('WebServerSG', sg.value),
                              ('DBUser', dbuser, True),
                              ('DBPassword', dbpass, True),
                              ('KeyName', 'firecares-dev', True)])


        click.secho('Updating NFIRS database security group with ingress from new web security group.')
        ec2.authorize_security_group(group_id='sg-13fd9e77', src_security_group_group_id=sg.value, ip_protocol='tcp',
                                     from_port=5432, to_port=5432)

    # If there are old stacks, flag them for deletion.
    old_stacks = [n for n in conn.describe_stacks() if 'firecares-dev-web' in n.stack_name and ami not in n.stack_name]

    for old_stack in old_stacks:
        delete_firecares_stack(old_stack)


@firecares_deploy.command()
@click.option('--name', prompt='Enter the stack name.', confirmation_prompt=True)
def delete_stack(name):
    """
    Deletes the stack and un-registers entries in various security groups the app needs access to.
    """
    delete_firecares_stack(name)


if __name__ == '__main__':
    firecares_deploy()