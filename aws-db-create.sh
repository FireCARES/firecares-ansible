# Create DB stack

# Burn AMI for rabbitmq
#packer build rabbitmq-prod-packer.json
# Grab AMI-ID and paste into firecares-staging_db.py

# Re-run firecares-staging_db.py
python stacks/firecares_staging_db.py > stacks/firecares-db-staging.json

aws cloudformation create-stack --stack-name firecares-prod --template-body file://stacks/firecares-db-staging.json --parameters file://stacks/firecares-db-params.json
cat stacks/firecares-db-staging.json > pre-web-deploy-db-template.json

python stacks/deploy.py delete_stack --name firecares-prod
