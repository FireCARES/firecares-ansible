#!/bin/sh

set -e

TMP=${TMP:-tmp}
DEPLOY_ENV=${DEPLOY_ENV:-dev}
CODE_LOCATION=${CODE_LOCATION:-../firecares}
DNS=${DNS:-staging.firecares.org}
URL=https://$DNS
DBPASS=${DBPASS:-}
DBUSER=${DBUSER:-}
PACKER=$(which packer) || PACKER=/usr/local/packer
PRIVATE_KEY_FILE=${PRIVATE_KEY_FILE:-}

if [ "$DBUSER" != "" ]; then
  echo "Using user: ${DBUSER} for database"
else
  echo "DB creds not included...pre-setup persistent db vs CF managed"
fi

echo "Temporary file location: ${TMP}"
echo "Deployment environment: ${DEPLOY_ENV}"
echo "FireCARES code location: ${CODE_LOCATION}"
echo "DNS entry for deployment: ${DNS}"
echo "URL: ${URL}"

mkdir -p $TMP
# Force a specific commit hash by commenting-out the following line
git -C $CODE_LOCATION rev-parse HEAD | cut -b 1-10 > $TMP/commit_hash.txt
HASH=$(cat $TMP/commit_hash.txt)

echo "Using commit hash: ${HASH}"

$PACKER build -machine-readable -color=false -var "commit=${HASH}" webserver-${DEPLOY_ENV}-packer.json | tee $TMP/packerlog.txt
cat $TMP/packerlog.txt | sed -n 's/^.*amazon-ebs,artifact.*AMIs were created.*\(ami.*\)$/\1/gp' > $TMP/current_ami.txt

# Check ami length, if 0 then abort
if [ $(wc -c < "$TMP/current_ami.txt") -eq 0 ]; then
  echo "AMI build failure, bailing..."
  exit 1
fi

AMI=$(cat $TMP/current_ami.txt)

echo AMI id: $AMI

if [ "$DBUSER" != "" ]; then
  python stacks/deploy.py deploy --env $DEPLOY_ENV --s3cors $URL --ami $AMI --commithash $HASH --dbpass $DBPASS --dbuser $DBUSER
else
  python stacks/deploy.py deploy --env $DEPLOY_ENV --s3cors $URL --ami $AMI --commithash $HASH
fi

CURRENT_TAG="tag_Name_web_server_${DEPLOY_ENV}_${HASH}"
echo Current web tags: $CURRENT_TAG
# Make sure that the new servers aren't included in the set to show the maintenance mode on
MAINT_HOSTS=$(python hosts/ec2.py | python to_inventory.py tag_Group_web_server_${DEPLOY_ENV} $CURRENT_TAG)

if [ "$MAINT_HOSTS" != "" ]; then
  echo Hosts to apply maintenance mode: $MAINT_HOSTS
  if [ "$PRIVATE_KEY_FILE" != "" ]; then
    ansible-playbook -vvvv -i hosts webservers-${DEPLOY_ENV}.yml --tags "maintenance_mode_on" -e "maintenance_mode=yes" --private-key=$PRIVATE_KEY_FILE --limit "tag_Group_web_server_${DEPLOY_ENV}:"'!'"$CURRENT_TAG"
  else
    ansible-playbook -vvvv -i hosts webservers-${DEPLOY_ENV}.yml --tags "maintenance_mode_on" -e "maintenance_mode=yes" --limit "tag_Group_web_server_${DEPLOY_ENV}:"'!'"$CURRENT_TAG"
  fi
else
  echo No hosts need to be set to maintenance mode, skipping...
fi

# Now, collectstatic, etc on the first current server
NEW_HOSTS=$(python hosts/ec2.py | python to_inventory.py $CURRENT_TAG)
echo New web IP addresses: $NEW_HOSTS
FIRST_NEW_HOST=$(echo $NEW_HOSTS | cut -d, -f 1)
echo Host to run collectstatic/migrations on: $FIRST_NEW_HOST
echo Sleeping for 60 seconds while we wait for SSH to open up on the new host...
sleep 60

if [ "$PRIVATE_KEY_FILE" != "" ]; then
  ansible-playbook -v -i hosts webservers-${DEPLOY_ENV}.yml --tags "django.syncdb,django.migrate,django.collectstatic" --extra-vars="run_django_sync_db=yes, run_django_db_migrations=yes, run_django_collectstatic=yes" --private-key=$PRIVATE_KEY_FILE --limit $CURRENT_TAG
else
  ansible-playbook -v -i hosts webservers-${DEPLOY_ENV}.yml --tags "django.syncdb,django.migrate,django.collectstatic" --extra-vars="run_django_sync_db=yes, run_django_db_migrations=yes, run_django_collectstatic=yes" --limit $CURRENT_TAG
fi

# Now, we can switch DNS over
python - <<- EOF
import sys
from boto.ec2 import elb
from boto.exception import BotoServerError
from boto.route53 import connect_to_region
from boto.route53.record import ResourceRecordSets

elb_conn = elb.connect_to_region('us-east-1')
r_conn = connect_to_region('us-east-1')

try:
    target = elb_conn.get_all_load_balancers(load_balancer_names=['firecares-$DEPLOY_ENV-$HASH'])[0]
except BotoServerError as e:
    print 'No load balancer defined as firecares-$DEPLOY_ENV-$HASH, skipping DNS update...'
    sys.exit(1)

zone = r_conn.get_zone('firecares.org')
record = zone.find_records('$DNS', 'A')
hosted_zone = record.alias_hosted_zone_id

alias = 'dualstack.{dns}.'.format(dns=target.dns_name.lower())

dest = 'ALIAS dualstack.{dns}. ({hosted_zone})'.format(dns=target.dns_name.lower(), hosted_zone=hosted_zone)

rrs = ResourceRecordSets(r_conn, zone.id)
cr = rrs.add_change('UPSERT', '$DNS', type='A',
                    alias_hosted_zone_id=hosted_zone,
                    alias_dns_name=alias,
                    alias_evaluate_target_health=False)
cr.add_value(dest)

rrs.commit()

print 'Set $DNS ALIAS to {alias}'.format(alias=dest)
EOF