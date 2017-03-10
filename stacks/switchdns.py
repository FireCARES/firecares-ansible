from boto.ec2 import elb
from boto.route53 import connect_to_region
from boto.route53.record import ResourceRecordSets

# hosted zone for elb on us-east-1
HOSTED_ZONE = 'Z35SXDOTRQ7X7K'

elb_conn = elb.connect_to_region('us-east-1')
r_conn = connect_to_region('us-east-1')

lbs = elb_conn.get_all_load_balancers()
zone = r_conn.get_zone('firecares.org.')

target = filter(lambda x: x.name.startswith('firecares-FireCARE'), lbs)[0]
alias = 'dualstack.{dns}.'.format(dns=target.dns_name.lower())

dest = 'ALIAS dualstack.{dns}. ({hosted_zone})'.format(dns=target.dns_name.lower(), hosted_zone=HOSTED_ZONE)

# rrs = ResourceRecordSets(r_conn, zone.id)
# cr = rrs.add_change('UPSERT', 'firecares.org.', type='A',
#                     alias_hosted_zone_id=HOSTED_ZONE,
#                     alias_dns_name=alias,
#                     alias_evaluate_target_health=False)
# cr.add_value(dest)
#
# rrs.commit()

print 'Set firecares.org ALIAS to {alias}'.format(alias=dest)
