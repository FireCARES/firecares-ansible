SFTP-Server
===========

An Ansible role which configures an OpenSSH server for chrooted SFTP access.  The role is built in such a way that it will not unnecessarily alter a user's OpenSSH customisations.  Instead, it simply changes the crucial bits that it needs to, and adds the rest of its configuration in the form of a custom config block (OpenSSH's lack of some form of conf.d/ support forces this behaviour).

Requirements
------------

It is advisable that `scp_if_ssh` be set to `true` in the `ssh_connection` section of your `ansible.cfg` file, seeing as how Ansible uses SFTP for file transfers by default, and you can easily lock yourself out of your server's SFTP by using this role.  The SCP fallback will continue to work.  Example config:

```ini
; ansible.cfg
...
[ssh_connection]
scp_if_ssh=True
```

Other than that, only Ansible itself is required.  Tested using Ansible 1.5 and 1.6.

Role Variables
--------------

The following role variables are relevant:

* `sftp_home_partition`: The partition where SFTP users' home directories will be located.  Defaults to "/home".
* `sftp_group_name`: The name of the Unix group to which all SFTP users must belong.  Defaults to "sftpusers".
* `sftp_directories`: A list of directories that need to be created automatically for each SFTP user.  Defaults to a blank list (i.e. "[]").
* `sftp_allow_passwords`: Whether or not to allow password authentication for SFTP. Defaults to False.
* `sftp_users`: A list of users, in map form, containing the following elements:
  * `name`: The Unix name of the user that requires SFTP access.
  * `password`: A password hash for the user to login with (leave blank if a key is used exclusively).
  * `authorized`: A list of files placed in `files/` which contain valid public keys for the SFTP user.


Example Playbook
-------------------------

```yaml
---
- name: test-playbook | Test sftp-server role
  hosts: all
  sudo: yes
  vars:
    - sftp_users:
      - name: peter
        password: "$1$salty$li5TXAa2G6oxHTDkqx3Dz/" # passpass
        authorized: []
      - name: sally
        password: ""
        authorized: [sally.pub]
    - sftp_directories:
      - imports
      - exports
      - other
  roles:
    - sftp-server
```

License
-------

Licensed under the MIT License. See the LICENSE file for details.
