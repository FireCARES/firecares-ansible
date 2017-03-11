#!/bin/sh

set -e

TMP=tmp
DEPLOY_ENV=prod
URL=https://staging.firecares.org
DBPASS=$DBPASS
DBUSER=$DBUSER

mkdir -p $TMP
git -C ../firecares rev-parse HEAD | cut -b 1-10 > $TMP/commit_hash.txt

#packer build -machine-readable -color=false -var "commit=$(cat ../commit_hash.txt)" webserver-$DEPLOY_ENV-packer.json | tee $TMP/packerlog.txt

cat $TMP/packerlog.txt | sed -n 's/^.*amazon-ebs,artifact.*AMIs were created.*\(ami.*\)$/\1/gp' > $TMP/current_ami.txt

# Check ami length, if 0 then abort
if [ $(wc -c < "$TMP/current_ami.txt") -eq 0 ]; then
  echo "AMI build failure, bailing..."
  exit 1
fi

AMI=$(cat $TMP/current_ami.txt)
HASH=$(cat $TMP/commit_hash.txt)

echo AMI: $AMI
echo Commit hash: $HASH

python stacks/deploy.py deploy --env prod --s3cors $URL --ami $AMI --commithash $HASH # --dbpass $DBPASS --dbuser $DBUSER

CURRENT_TAG="tag_Name_web_server_${DEPLOY_ENV}_$HASH"
echo Current web tags: $CURRENT_TAG
# Make sure that the new servers aren't included in the set to show the maintenance mode on
MAINT_HOSTS=$(python hosts/ec2.py | python to_inventory.py tag_Group_web_server_prod $CURRENT_TAG)

if [ "$MAINT_HOSTS" = "" ]; then
  #TODO: Need to test
  echo Hosts to apply maintenance mode: $MAINT_HOSTS
  echo ansible-playbook -v -i hosts webservers-prod.yml --tags "maintenance_mode_off" -e "maintenance_mode=yes" --private-key=~/.ssh/firecares-prod.pem --limit "tag_Group_web_server_prod:"'!'"$CURRENT_TAG"
else
  echo No hosts need to be set to maintenance mode, skipping...
fi

# Now, collectstatic, etc on the first current production server
NEW_HOSTS=$(python hosts/ec2.py | python to_inventory.py $CURRENT_TAG)
echo New web IP addresses: $NEW_HOSTS
FIRST_NEW_HOST=$($NEW_HOSTS | cut -d, -f 1)
echo Host to run collectstatic/migrations on: $FIRST_NEW_HOST
echo ansible-playbook -v -i hosts webservers-prod.yml --tags "django.syncdb,django.migrate,django.collectstatic" --extra-vars="run_django_sync_db=yes, run_django_db_migrations=yes, run_django_collectstatic=yes" --private-key=~/.ssh/firecares-prod.pem --limit $CURRENT_TAG[0]

# Now, we can switch DNS over
# python - <<- EOF
# from boto.ec2 import elb
# from boto.route53 import connect_to_region
# from boto.route53.record import ResourceRecordSets
#
# # hosted zone for elb on us-east-1
# HOSTED_ZONE = 'Z35SXDOTRQ7X7K'
#
# elb_conn = elb.connect_to_region('us-east-1')
# r_conn = connect_to_region('us-east-1')
#
# target = elb_conn.get_all_load_balancers(load_balancer_names=['firecares-prod-$HASH'])[0]
# zone = r_conn.get_zone('firecares.org.')
#
# alias = 'dualstack.{dns}.'.format(dns=target.dns_name.lower())
#
# dest = 'ALIAS dualstack.{dns}. ({hosted_zone})'.format(dns=target.dns_name.lower(), hosted_zone=HOSTED_ZONE)
#
# rrs = ResourceRecordSets(r_conn, zone.id)
# cr = rrs.add_change('UPSERT', 'firecares.org.', type='A',
#                     alias_hosted_zone_id=HOSTED_ZONE,
#                     alias_dns_name=alias,
#                     alias_evaluate_target_health=False)
# cr.add_value(dest)
#
# rrs.commit()
#
# print 'Set firecares.org ALIAS to {alias}'.format(alias=dest)
# EOF
