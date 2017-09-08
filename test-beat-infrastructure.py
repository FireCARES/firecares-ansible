import os
import re
from urlparse import urlparse

def get_env(src):
    ret = {}
    for l in src.splitlines():
        mat = re.match('export\s+([^=]+)="?([^"]+)"?', l)
        if mat:
            groups = mat.groups()
            ret[groups[0]] = groups[1]
    return ret


def test_db_connection(host):
    with host.sudo():
        env = get_env(host.run('cat /webapps/firecares/bin/postactivate').stdout)

    db = env['DATABASE_HOST']
    host.run_expect([0], 'nc -w 2 -z {} 5432'.format(db))


def test_rabbit_connection(host):
    with host.sudo():
        env = get_env(host.run('cat /webapps/firecares/bin/postactivate').stdout)

    rabbit = urlparse(env['BROKER_URL']).hostname
    host.run_expect([0], 'nc -w 2 -z {} 5672'.format(rabbit))


def test_nginx_not_running_and_disabled(host):
    nginx = host.service("nginx")
    assert not nginx.is_running
    assert not nginx.is_enabled


def test_celery_running(host):
    with host.sudo():
        assert host.supervisor('celery').is_running


def test_gunicorn_stopped(host):
    with host.sudo():
        assert not host.supervisor('firecares').is_running
