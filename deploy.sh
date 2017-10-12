#!/bin/bash

set -e

EXISTING_HASH=${HASH:-}
TMP=${TMP:-tmp}
DEPLOY_ENV=${DEPLOY_ENV:-dev}
CODE_LOCATION=${CODE_LOCATION:-../firecares}
DNS=${DNS:-staging.firecares.org}
URL=https://$DNS
DBPASS=${DBPASS:-}
DBUSER=${DBUSER:-}
RUN_MIGRATIONS=${RUN_MIGRATIONS:-0}
PACKER=$(which packer) || PACKER=/usr/local/packer
PRIVATE_KEY_FILE=${PRIVATE_KEY_FILE:-~/.ssh/id_rsa}
BOLD="\033[1m"
BOLDOFF="\033[0m"
START=$(date +%s)
STEPS=8
EXISTING=0
KEEP=${KEEP:-2}

if [ "$DBUSER" != "" ]; then
  echo "Using user: ${DBUSER} for database"
else
  echo "DB creds not included...pre-setup persistent db vs CF managed"
fi

echo -e "Temporary file location: ${BOLD}${TMP}${BOLDOFF}"
echo -e "Deployment environment: ${BOLD}${DEPLOY_ENV}${BOLDOFF}"
echo -e "FireCARES code location: ${BOLD}${CODE_LOCATION}${BOLDOFF}"
echo -e "DNS entry for deployment: ${BOLD}${DNS}${BOLDOFF}"
echo -e "URL: ${BOLD}${URL}${BOLDOFF}"

mkdir -p $TMP

stepavg() {
  if [ -f "$TMP/$1.txt" ]; then
    TOT=$(awk '{ sum += $1 } END { print sum }' $TMP/$1.txt)
    LINES=$(wc -l < $TMP/$1.txt | tr -d ' ')
    if [ $LINES -gt 0 ]; then
      local avg=$(( $TOT / $LINES ))
      if [ $avg -le 60 ]; then
        echo -e "Average time to run: $avg seconds"
      else
        local t=$(bc -l <<< "scale=2; $avg/60")
        echo -e "Average time to run: $t minutes"
      fi
    fi
  fi
}

step() {
  CURSTEP=$1
  echo -e "${BOLD}STEP [$1/${STEPS}]${BOLDOFF} $2"
}

start() {
  DT=$(date +%s)
}

stop() {
  STOP=$(( `date +%s` - $DT ))
}

saveTime() {
  echo $1 >> $TMP/$2.txt
}

getHash() {
  step 1 "Get commit hash"
  stepavg 1
  start

  if [ "$1" != "" ]; then
    echo -e "${BOLD}Using passed-in hash for deployment => ${1}${BOLDOFF}"
    HASH=$1
    EXISTING=1
  else
    # Force a specific commit hash by commenting-out the following line
    echo "$(git -C $CODE_LOCATION rev-parse HEAD | cut -b 1-6)-$(date +%Y%m%d-%H%M)" > $TMP/commit_hash.txt
    HASH=$(cat $TMP/commit_hash.txt)
  fi

  echo -e "Using commit hash: ${BOLD}${HASH}${BOLDOFF}"
  stop
  saveTime $STOP 1
}

packWebAMI() {
  step 2 "Pack web AMI"
  stepavg 2
  start

  EXISTING_AMI=$(aws ec2 describe-images --owners self --filters "Name=name,Values=webserver-${DEPLOY_ENV}-${HASH}")
  if [ "$(echo $EXISTING_AMI | wc -w)" -lt 10 ]; then
    echo "AMI for webserver-${DEPLOY_ENV}-${HASH} not found...creating"
    $PACKER build -machine-readable -color=false -var "commit=${HASH}" packer/web/webserver-${DEPLOY_ENV}-packer.json | tee $TMP/packerlog.txt
    cat $TMP/packerlog.txt | egrep 'artifact,0,id' | rev | cut -f1 -d: | rev > $TMP/current_ami.txt
    # Check ami length, if 0 then abort
    if [ $(wc -c < "$TMP/current_ami.txt") -eq 0 ]; then
      echo "AMI build failure, bailing..."
      exit 1
    fi

    AMI=$(cat $TMP/current_ami.txt)
  else
    AMI=$(echo $EXISTING_AMI | python -c "import json,sys;j=json.load(sys.stdin);print j['Images'][0]['ImageId']")
    echo "Re-deploying using existing AMI"
  fi

  echo "AMI id: $AMI"
  stop
  if [ "$EXISTING" -eq "0" ]; then
    saveTime $STOP 2
  fi
}

packBeatAMI() {
  step 3 "Pack beat AMI"
  stepavg 3
  start

  EXISTING_BEATAMI=$(aws ec2 describe-images --owners self --filters "Name=name,Values=celerybeat-${DEPLOY_ENV}-${HASH}")

  if [ "$(echo $EXISTING_BEATAMI | wc -w)" -lt 10 ]; then
    echo "AMI for celerybeat-${DEPLOY_ENV}-${HASH} not found...creating"
    $PACKER build -machine-readable -color=false -var "commit=${HASH}" packer/celerybeat/celerybeat-${DEPLOY_ENV}-packer.json | tee $TMP/beatpackerlog.txt
    cat $TMP/beatpackerlog.txt | egrep 'artifact,0,id' | rev | cut -f1 -d: | rev > $TMP/beatcurrent_ami.txt
    # Check ami length, if 0 then abort
    if [ $(wc -c < "$TMP/beatcurrent_ami.txt") -eq 0 ]; then
      echo "Beat AMI build failure, bailing..."
      exit 1
    fi

    BEATAMI=$(cat $TMP/beatcurrent_ami.txt)
  else
    BEATAMI=$(echo $EXISTING_BEATAMI | python -c "import json,sys;j=json.load(sys.stdin);print j['Images'][0]['ImageId']")
    echo "Re-deploying using existing beat AMI"
  fi

  echo -e "BEAT AMI id: ${BOLD}$BEATAMI${BOLDOFF}"
  stop
  if [ "$EXISTING" -eq "0" ]; then
    saveTime $STOP 3
  fi
}

deploy() {
  step 4
  stepavg 4
  start

  if [ "$DBUSER" != "" ]; then
    #echo python deploy.py deploy --env $DEPLOY_ENV --s3cors $URL --ami $AMI --beatami $BEATAMI --commithash $HASH --dbpass $DBPASS --dbuser $DBUSER
    python deploy.py deploy --env $DEPLOY_ENV --s3cors $URL --ami $AMI --beatami $BEATAMI --commithash $HASH --keep $KEEP --dbpass $DBPASS --dbuser $DBUSER
  else
    #echo python deploy.py deploy --env $DEPLOY_ENV --s3cors $URL --ami $AMI --beatami $BEATAMI --commithash $HASH
    python deploy.py deploy --env $DEPLOY_ENV --s3cors $URL --ami $AMI --beatami $BEATAMI --commithash $HASH --keep $KEEP
  fi

  stop
  saveTime $STOP 4
}

maintOn() {
  step 5
  stepavg 5
  start

  CURRENT_TAG="tag_Name_web_server_${DEPLOY_ENV}_$(echo $HASH | tr - _)"
  echo "Current web tags: $CURRENT_TAG"

  # Make sure that the new servers aren't included in the set to show the maintenance mode on
  MAINT_HOSTS=$(python hosts/ec2.py | python to_inventory.py tag_Group_web_server_${DEPLOY_ENV} $CURRENT_TAG)
  PRIMARY_HOST=$(python hosts/ec2.py | python to_inventory.py $CURRENT_TAG | sed -e "s/,.*//g"),

  if [ "$RUN_MIGRATIONS" != "0" ]; then
    if [ "$MAINT_HOSTS" != "" ]; then
      echo "Hosts to apply maintenance mode: $MAINT_HOSTS"
      # echo ansible-playbook -vvvv -i $MAINT_HOSTS webservers-${DEPLOY_ENV}.yml --tags "maintenance_mode_on" -e "maintenance_mode=yes" --private-key=$PRIVATE_KEY_FILE
      ansible-playbook -vvvv webservers-${DEPLOY_ENV}.yml --tags "maintenance_mode_on" -e "maintenance_mode=yes" --private-key=$PRIVATE_KEY_FILE --limit $MAINT_HOSTS
    else
      echo "No hosts need to be set to maintenance mode, skipping..."
    fi
  fi

  stop
  saveTime $STOP 5
}

migrateCollectStatic() {
  step 6
  stepavg 6
  start

  # Now, collectstatic, etc on the first current server
  NEW_HOSTS=$(python hosts/ec2.py | python to_inventory.py $CURRENT_TAG)
  echo -e "New web IP addresses: ${BOLD}$NEW_HOSTS${BOLDOFF}"
  FIRST_NEW_HOST=$(echo $NEW_HOSTS | cut -d, -f 1)
  echo "Host to run collectstatic/migrations on: $FIRST_NEW_HOST"
  echo "Waiting for SSH to open..."

  SSH_CMD="ssh -i $PRIVATE_KEY_FILE -o ConnectTimeout=5 -o StrictHostKeyChecking=no ubuntu@$FIRST_NEW_HOST exit 2>&1"

  set +e
  eval $SSH_CMD
  OPEN=$?

  while [ "$OPEN" -gt 0 ]; do
    eval $SSH_CMD
    OPEN=$?
    echo "SSH not open on $FIRST_NEW_HOST"
    sleep 20
  done

  set -e

  # $(ssh -t -i $PRIVATE_KEY_FILE ubuntu@$FIRST_NEW_HOST << EOF
  # sudo -u firecares sh -c "cd /webapps/firecares/; . bin/activate; cd firecares; python manage.py migrate --list | grep '\[\s\]'"
  # EOF
  # )

  if [ "$RUN_MIGRATIONS" != "0" ]; then
    ansible-playbook -vvvv webservers-${DEPLOY_ENV}.yml --tags "django.syncdb,django.migrate,django.collectstatic,django.generate_sitemap" --extra-vars="run_django_sync_db=yes, run_django_db_migrations=yes, run_django_collectstatic=yes, generate_sitemap=yes" --private-key=$PRIVATE_KEY_FILE --limit $PRIMARY_HOST
  else
    ansible-playbook -vvvv webservers-${DEPLOY_ENV}.yml --tags "django.collectstatic" --extra-vars="run_django_collectstatic=yes" --private-key=$PRIVATE_KEY_FILE --limit $PRIMARY_HOST
  fi

  stop
  saveTime $STOP 6
}

dnsSwitch() {
  step 7
  stepavg 7
  start
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
    target = elb_conn.get_all_load_balancers(load_balancer_names=['fc-$DEPLOY_ENV-$HASH'])[0]
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

  stop
  saveTime $STOP 7
}

turnOffOld() {
  step 8
  stepavg 8
  start

  ALL_HOSTS=$(python hosts/ec2.py | jq "to_entries[] | select(.key | test(\"tag_Name_(celerybeat|web_server)_${DEPLOY_ENV}\")).value | join(\",\")" | paste -sd "," - | tr -d '\"')
  echo $ALL_HOSTS

  CURRENT_TAG="tag_Name_web_server_${DEPLOY_ENV}_$(echo $HASH | tr - _)"
  CURRENT_BEAT_TAG="tag_Name_celerybeat_${DEPLOY_ENV}_$(echo $HASH | tr - _)"
  echo "Current web tags: $CURRENT_TAG"

  # Make sure that the new servers aren't included in the set to show the maintenance mode on
  MAINT_HOSTS=$(python hosts/ec2.py | python to_inventory.py tag_Group_web_server_${DEPLOY_ENV} $CURRENT_TAG)

  if [ "$MAIN_HOSTS" != "" ]; then
    # Wait for a little bit before spinning down the old webservers/celery servers
    sleep 60
    echo "Web hosts to turn off: $MAINT_HOSTS"
    # echo ansible-playbook -vvvv -i $MAINT_HOSTS webservers-${DEPLOY_ENV}.yml --tags "maintenance_mode_on" -e "maintenance_mode=yes" --private-key=$PRIVATE_KEY_FILE
    ansible-playbook -vvvv webservers-${DEPLOY_ENV}.yml --tags "maintenance_mode_on" -e "maintenance_mode=yes" --private-key=$PRIVATE_KEY_FILE --limit $MAINT_HOSTS
  else
    echo "No web hosts to turn off"
  fi

  if [ "$BEAT_MAINT_HOSTS" != "" ]; then
    BEAT_MAINT_HOSTS=$(python hosts/ec2.py | python to_inventory.py tag_Group_celerybeat_${DEPLOY_ENV} $CURRENT_BEAT_TAG)

    echo "Beat hosts to turn off: $BEAT_MAINT_HOSTS"
    ansible-playbook -vvvv webservers-${DEPLOY_ENV}.yml --tags "maintenance_mode_on" -e "maintenance_mode=yes" --private-key=$PRIVATE_KEY_FILE --limit $BEAT_MAINT_HOSTS
  else
    echo "No beat hosts to turn off"
  fi

  stop
  saveTime $STOP 8
}

echo "Started: $(date)"
getHash $EXISTING_HASH # Force a redeploy by passing a specific commit hash to "getHash", eg. getHash "3efcc2-20170906-1613", skips the packer steps
packWebAMI
packBeatAMI
deploy
maintOn
migrateCollectStatic
dnsSwitch
turnOffOld
echo "Ended: $(date)"
echo -e "${BOLD}Took: $(( `date +%s` - $START )) seconds${BOLDOFF}"
echo $(( `date +%s` - $START )) >> $TMP/duration.txt
