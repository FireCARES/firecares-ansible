#!/bin/bash

ENV=${ENV:-dev}
# Env = dev|prod

WEB_HOSTS=$(python deploy.py list_machines --env=$ENV --onlyweb)
BEAT_HOSTS=$(python deploy.py list_machines --env=$ENV --onlybeat)

BOLD="\033[1m"
BOLDOFF="\033[0m"

while IFS=',' read -ra CONN; do
  for i in "${CONN[@]}"; do
    echo -e "\n\n\n${BOLD}Running sanity checks for WEB server(s) on ${ENV}: ${i}${BOLDOFF}\n\n\n"
    testinfra -s -v --connection=ssh --hosts=ubuntu@${i} --ssh-identity-file=~/.ssh/firecares-${ENV}.pem test-web-infrastructure.py
  done
done <<< "$WEB_HOSTS"

while IFS=',' read -ra CONN; do
  for i in "${CONN[@]}"; do
    echo -e "\n\n\n${BOLD}Running sanity checks for BEAT server(s) on ${ENV}: ${i}${BOLDOFF}\n\n\n"
    testinfra -s -v --connection=ssh --hosts=ubuntu@${i} --ssh-identity-file=~/.ssh/firecares-${ENV}.pem test-beat-infrastructure.py
  done
done <<< "$BEAT_HOSTS"
