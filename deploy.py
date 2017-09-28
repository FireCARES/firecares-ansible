import click
import time
import sh
import os
import datetime
import re
import sys
from tabulate import tabulate
from boto.cloudformation.connection import CloudFormationConnection
from boto.cloudformation.stack import Stack
from boto import connect_ec2
from boto.exception import BotoServerError, EC2ResponseError
from boto.ec2 import elb
from boto.ec2.autoscale import AutoScaleConnection
from boto.ec2.connection import EC2Connection
from boto.route53 import connect_to_region
from boto.route53.record import ResourceRecordSets
from stacks.firecares_db import t as db_server_stack
from stacks.firecares_web import t as web_server_stack
from stacks.firecares_staging_db import t as db_staging_server_stack

DNS = {
    'dev': 'test.firecares.org',
    'prod': 'firecares.org'
}


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

    ws = get_web_security_group(stack_or_name)
    if ws:
        old_sg = ws.value
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


def _get_commit_hash(location='../firecares'):
    if sh.git('-C', location, 'diff', _tty_out=False).stdout or sh.git('-C', location, 'diff', '--cached', _tty_out=False).stdout:
        click.secho('WARNING: There are unstaged changes, deployment uses the github repository when packing images!', fg='yellow')

    chash = sh.git('-C', location, 'rev-parse', 'HEAD').stdout[0:6]
    dt = datetime.datetime.now().strftime('%Y%m%d-%H%M')
    return '{}-{}'.format(chash, dt)


@click.group(invoke_without_command=True)
@click.pass_context
def firecares_deploy(ctx):
    if ctx.invoked_subcommand is None:
        click.secho(r"""FireCARES Deployment Script""", fg='green')
        click.echo(firecares_deploy.get_help(ctx))
    return ctx.invoked_subcommand


@firecares_deploy.command()
@click.option('--env', default='dev')
def full_deploy(env):
    # Generate commit hash
    curhash = _get_commit_hash()
    click.secho('Packing web/celery VMs using FireCARES commit hash/date: {}'.format(curhash), fg='green')

    # Pack webserver AMI

    # Pack beat AMI

    # run "deploy" (deploys cloudformation stack)
    # - switch to maintenance mode if there are migrations
    # - run migrations on first node
    # collecstatic on first host
    # Switch DNS
    # switch maintenance mode off (if needed)
    pass


@firecares_deploy.command()
@click.option('--ami', help='Currently deployed AMI')
@click.option('--keep', default=2, help='# of stacks to keep in AWS')
@click.option('--env', default='dev', help='Environment (dev/prod)')
def delete_old_stacks(ami, keep, env):
    """
    Delete old FireCARES webserver CloudFormation stacks from AWS.
    """
    _delete_old_stacks(ami, keep, env)


@firecares_deploy.command()
@click.option('--env', default='dev', help='Environment (dev|prod)')
@click.option('--hash', default='')
@click.option('--path', default='')
def test(env, hash, path):
    res = sh.ls('-al', _iter=True)
    for r in res:
        print r,


@firecares_deploy.command()
@click.option('--env', default='dev', help='Environment (dev|prod)')
@click.option('--commithash', default='')
def pack_webserver(env, commithash):
    if not commithash:
        commithash = _get_commit_hash()
    path = 'packer/web/webserver-{}-packer.json'.format(env)
    res = sh.packer("build", "-machine-readable", "-var", "commit=" + commithash, path, _iter=True)
    for r in res:
        print r,


@firecares_deploy.command()
@click.option('--env', default='dev', help='Environment (dev|prod)')
@click.option('--hash', default='')
def switch_dns(env, hash):
    """
    Switches DNS to latest ELB in specified FireCARES environment.
    """

    dns = DNS[env]

    elb_conn = elb.connect_to_region('us-east-1')
    r_conn = connect_to_region('us-east-1')

    lbs = elb_conn.get_all_load_balancers()
    fclbs = sorted(filter(lambda x: x.name.startwith('fc-{}'.format(env)), lbs), key=lambda x: x.name)
    if not fblbs:
        print 'No load balancer for env: {}'.format(env)
        sys.exit(1)
    elif len(fblbs) == 1:
        print 'WARNING: Only 1 load balancer in place, potential for no effect on DNS switch'
    target = fclbs[0]

    zone = r_conn.get_zone('firecares.org')
    record = zone.find_records(dns, 'A')
    hosted_zone = record.alias_hosted_zone_id

    alias = 'dualstack.{dns}.'.format(dns=target.dns_name.lower())

    dest = 'ALIAS dualstack.{dns}. ({hosted_zone})'.format(dns=target.dns_name.lower(), hosted_zone=hosted_zone)

    rrs = ResourceRecordSets(r_conn, zone.id)
    cr = rrs.add_change('UPSERT', dns, type='A',
                        alias_hosted_zone_id=hosted_zone,
                        alias_dns_name=alias,
                        alias_evaluate_target_health=False)
    cr.add_value(dest)

    rrs.commit()

    print 'Set {dns} ALIAS to {alias}'.format(dns=dns, alias=dest)


@firecares_deploy.command()
@click.option('--ami', default='AMI', help='AMI to deploy')
@click.option('--beatami', default='BEATAMI', help='Celery beat AMI to use')
@click.option('--env', default='dev', help='Environment (dev|prod)')
@click.option('--commithash', help='The hash of the commit used to generate the AMI')
@click.option('--dbpass', help='Database password from firecares-db stack.')
@click.option('--dbuser', help='Database user from firecares-db stack.')
@click.option('--s3cors', default='*', help='S3 CORS allowed hosts')
@click.option('--keep', default=2, help='Number of CloudFormation stacks to keep (including currently deployed)')
def deploy(ami, beatami, env, commithash, dbpass, dbuser, s3cors, keep):
    """
    Deploys a firecares environment/CloudFormation stack w/ security group tweaks.

    Note: This currently assumes the db stack is already created.
    """

    if keep < 2:
        keep = 1
    conn = CloudFormationConnection()
    ec2 = connect_ec2()

    db_stack = '-'.join(['firecares', env])
    key_name = '-'.join(['firecares', env])

    name = 'firecares-{env}-web-{commithash}'.format(env=env, commithash=commithash)

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
                              ('CommitHash', commithash),
                              ('beatAmi', beatami)])

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

    _delete_old_stacks(ami=ami, env=env, keep=keep)


@firecares_deploy.command()
@click.option('--name', prompt='Enter the stack name.', confirmation_prompt=True)
def delete_stack(name):
    """
    Deletes stack and un-register entries in various security groups the app needs access to.
    """
    delete_firecares_stack(name)


def get_deployed_web_stack(env):
    conn = CloudFormationConnection()
    r_conn = connect_to_region('us-east-1')
    zone = r_conn.get_zone('firecares.org')

    if env == 'dev':
        dns = get_dns_root(zone.get_a('test.firecares.org').alias_dns_name)
    elif env == 'prod':
        dns = get_dns_root(zone.get_a('firecares.org').alias_dns_name)

    to_prune = 'firecares-{env}-web-'.format(env=env)
    stacks = [x for x in conn.describe_stacks() if x.stack_name.startswith(to_prune) and dns in x.stack_name]
    return next(iter(stacks), None)


def get_dns_root(s):
    return re.match('dualstack\.fc-(prod|dev)-(.*)-\d+\.us-east-1\.elb\.amazonaws\.com\.', s).groups()[1]


@firecares_deploy.command()
@click.option('--env', default='dev', help='Environment (dev|prod)')
@click.option('--onlyweb', default=False, is_flag=True)
@click.option('--onlybeat', default=False, is_flag=True)
def list_machines(env, onlyweb, onlybeat):
    econn = EC2Connection()
    agconn = AutoScaleConnection()
    cfconn = CloudFormationConnection()
    stack = get_deployed_web_stack(env)

    verbose = not onlyweb and not onlybeat

    if onlyweb or verbose:
        asg_id = stack.describe_resources('WebserverAutoScale')[0].physical_resource_id
        # Get web instances in the autoscaling group
        asg = agconn.get_all_groups([asg_id])[0]
        inst_ids = [i.instance_id for i in asg.instances]
        reservations = econn.get_all_instances(instance_ids=inst_ids)
        instances = [i.public_dns_name for r in reservations for i in r.instances]
        click.secho('{}{}'.format('web: ' if verbose else '', ','.join(instances)))

    # Get beat instance in stack
    if onlybeat or verbose:
        beat = stack.describe_resources('BeatInstance')
        if beat:
            beat_id = beat[0].physical_resource_id
            beatinst = econn.get_all_instances(instance_ids=[beat_id])[0].instances[0]
            click.secho('{}{}'.format('beat: ' if verbose else '', beatinst.public_dns_name))

@firecares_deploy.command()
def list_stacks():
    """
    Display FireCARES CloudFormation stacks.
    """
    conn = CloudFormationConnection()
    econn = EC2Connection()
    r_conn = connect_to_region('us-east-1')
    zone = r_conn.get_zone('firecares.org')

    test = zone.get_a('test.firecares.org').alias_dns_name
    prod = zone.get_a('firecares.org').alias_dns_name

    def get_failures(stack):
        return ' | '.join(set([x.resource_status_reason for x in stack.describe_events()[:10] if x.resource_status.endswith('FAILED')]))

    def get_deployed(stack):
        if 'dev-web' in stack.stack_name:
            if get_dns_root(test) == stack.stack_name.strip('firecares-dev-web-'):
                return 'test.firecares.org'
        elif 'prod-web' in stack.stack_name:
            if get_dns_root(prod) == stack.stack_name.strip('firecares-prod-web-'):
                return 'firecares.org'

    rows = [[x.stack_name, x.stack_status, x.creation_time.isoformat(), get_deployed(x), get_failures(x)] for x in conn.describe_stacks() if x.stack_name.startswith('firecares')]
    click.secho(tabulate(rows, headers=['NAME', 'STATUS', 'CREATED AT', 'LIVE @', 'ERRORS']))


if __name__ == '__main__':
    firecares_deploy()
