#!/bin/sh
source ./tmp/dbcreds

DBUSER=$DBUSER DBPASS=$DBPASS DNS=test.firecares.org PRIVATE_KEY_FILE=~/.ssh/firecares-dev.pem ./deploy.sh
