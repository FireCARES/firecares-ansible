#!/bin/sh

# Pass maintenance mode via "MODE" environment variable on = display maintenance mode and off = turn off maintenance mode
MODE=maintenance_mode_${MODE:-on}
ENV=${ENV:-dev}

echo "Switching maintenance mode: ${MODE}"
echo "Environment = ${ENV}"

ansible-playbook -vvvv -i hosts webservers-${ENV}.yml --tags "$MODE" -e "maintenance_mode=yes" --private-key=~/.ssh/firecares-${ENV}.pem --limit "tag_Group_web_server_${ENV}"
