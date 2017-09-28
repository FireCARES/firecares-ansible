#!/bin/sh
source ./tmp/dbcreds

DBUSER=$DBUSER DBPASS=$DBPASS DNS=test.firecares.org RUN_MIGRATIONS=0 PRIVATE_KEY_FILE=~/.ssh/firecares-dev.pem KEEP=1 ./deploy.sh
