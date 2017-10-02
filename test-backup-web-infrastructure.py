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


def test_celery_not_running(host):
    with host.sudo():
        assert not host.supervisor('celery').is_running


def test_gunicorn_not_running(host):
    with host.sudo():
        assert not host.supervisor('firecares').is_running
