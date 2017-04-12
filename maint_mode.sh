#!/bin/sh

MODE=maintenance_mode_${MODE:on}

ansible-playbook -vvvv -i hosts webservers-prod.yml --tags "$MODE" -e "maintenance_mode=yes" --private-key=~/.ssh/firecares-prod.pem --limit "tag_Group_web_server_prod"
