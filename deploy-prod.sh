#!/bin/sh

DNS=firecares.org DEPLOY_ENV=prod RUN_MIGRATIONS=0 PRIVATE_KEY_FILE=~/.ssh/firecares-prod.pem ./deploy.sh
