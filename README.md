firecares-ansible
=================
The Devops Repo for FireCARES

Ansible Playbook that installs and configures these applications that are commonly used in production Django deployments:

- Nginx
- Gunicorn
- PostgreSQL
- Supervisor
- Virtualenv
- Memcached
- Celery
- RabbitMQ

Default settings are stored in ```roles/role_name/vars/main.yml```.  Environment-specific settings are in the ```env_vars``` directory.

**Tested with OS:** Ubuntu 14.04 LTS x64

## Getting Started

A quick way to get started is with Vagrant and VirtualBox.

### Requirements

- [Ansible](http://docs.ansible.com/intro_installation.html)
- [Vagrant](http://www.vagrantup.com/downloads.html)
- [VirtualBox](https://www.virtualbox.org/wiki/Downloads)

```
git clone https://github.com/FireCARES/firecares-ansible.git
git clone https://github.com/FireCARES/firecares.git
cd firecares-ansible
vagrant up
```

Wait a few minutes for the magic to happen.  Access the app by going to this URL: http://192.168.33.15

### Additional vagrant commands

**SSH to the box**

```
vagrant ssh
```

**Re-provision the box to apply the changes you made to the Ansible configuration**

```
vagrant provision
```

**Reboot the box**

```
vagrant reload
```

**Shutdown the box**

```
vagrant halt
```

## Running the Ansible Playbook to provision servers

First, create an inventory file for the environment, for example:

```
# development

[all:vars]
env=dev

[webservers]
webserver1.example.com
webserver2.example.com

[dbservers]
dbserver1.example.com
```

Next, create a playbook for the server type. See [webservers.yml](webservers.yml) for an example.

Run the playbook:

```
ansible-playbook -i development webservers.yml
```

You can also provision an entire site by combining multiple playbooks.  For example, I created a playbook called `site.yml` that includes both the `webservers.yml` and `dbservers.yml` playbook.

A few notes here:

- The `dbservers.yml` playbook will only provision servers in the `[dbservers]` section of the inventory file.
- The `webservers.yml` playbook will only provision servers in the `[webservers]` section of the inventory file.
- An inventory var called `env` is also set which applies to `all` hosts in the inventory.  This is used in the playbook to determine which `env_var` file to use.

You can then provision the entire site with this command:

```
ansible-playbook -i development site.yml
```

If you're testing with vagrant, you can use this command:

```
ansible-playbook -i vagrant_ansible_inventory_default --private-key=~/.vagrant.d/insecure_private_key vagrant.yml
```

## Useful Links

- [Ansible - Getting Started](http://docs.ansible.com/intro_getting_started.html)
- [Ansible - Best Practices](http://docs.ansible.com/playbooks_best_practices.html)
- [Setting up Django with Nginx, Gunicorn, virtualenv, supervisor and PostgreSQL](http://michal.karzynski.pl/blog/2013/06/09/django-nginx-gunicorn-virtualenv-supervisor/)
- [How to deploy encrypted copies of your SSL keys and other files with Ansible and OpenSSL](http://www.calazan.com/how-to-deploy-encrypted-copies-of-your-ssl-keys-and-other-files-with-ansible-and-openssl/)

