from troposphere import Ref, Template, Parameter, GetAZs, Output, Join, GetAtt
from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup, Tag
from troposphere.ec2 import Instance, SecurityGroup, SecurityGroupRule, EIP
from troposphere.elasticloadbalancing import LoadBalancer, AccessLoggingPolicy
from troposphere.rds import DBInstance, DBParameterGroup, DBSecurityGroup, DBSecurityGroupIngress, RDSSecurityGroup
from troposphere.s3 import Bucket, PublicRead, CorsConfiguration, CorsRules

t = Template()
t.add_description("Create a FireCARES Instance")

base_ami = "ami-d05e75b8"

key_name = t.add_parameter(Parameter(
    "KeyName",
    Description="Name of an existing EC2 KeyPair to enable SSH access to the instances",
    Type="AWS::EC2::KeyPair::KeyName",
    ConstraintDescription="Must be the name of an existing EC2 KeyPair."
))

s3_static_allowed_cors_origin = t.add_parameter(Parameter(
    "S3StaticAllowedCORSOrigin",
    Description="Name of the allowed origins for accessing the static FireCARES S3 bucket",
    Type="CommaDelimitedList",
    ConstraintDescription="Must be a set of origins (including scheme://host)"
))

webserver_sg = t.add_parameter(Parameter(
    "WebServerSG",
    Description="The GroupID of the Webserver Security Group",
    Type="String",
    ConstraintDescription="Must be the name of an existing security group",
    Default="sg-ee029092"
))

vpc_id = t.add_parameter(Parameter(
    "VpcId",
    Description="Name of an existing vpc",
    Type="String",
    Default="vpc-fc94c499",
    ConstraintDescription="must be an existing VPC name."
))

db_user = t.add_parameter(Parameter(
    "DBUser",
    NoEcho=True,
    Description="Username for PostgreSQL database access",
    Type="String",
    ConstraintDescription="Must begin with a letter and contain only alphanumeric characters.",
    MinLength=1,
    MaxLength=16,
    AllowedPattern="[a-zA-Z][a-zA-Z0-9]*",
))

db_password = t.add_parameter(Parameter(
    "DBPassword",
    NoEcho=True,
    Description="Password for PostgreSQL database access",
    Type="String",
    ConstraintDescription="must contain only alphanumeric characters.",
    MinLength=8,
    MaxLength=41,
    AllowedPattern="[a-zA-Z0-9]*",
))

db_storage = t.add_parameter(Parameter(
    "DBAllocatedStorage",
    Description="The size of the database (Gb)",
    Type="Number",
    ConstraintDescription="must be between 10 and 1024Gb.",
    MinValue="10",
    MaxValue="1024",
    Default="10"
))

db_instance_class = t.add_parameter(Parameter(
    "DBInstanceClass",
    Description="The database instance type",
    Type="String",
    ConstraintDescription="must select a valid database instance type.",
    Default="db.t2.small",
    AllowedValues=[
        "db.t1.micro",
        "db.m1.small",
        "db.m1.medium",
        "db.m1.large",
        "db.m1.xlarge",
        "db.m2.xlarge",
        "db.m2.2xlarge",
        "db.m2.4xlarge",
        "db.m3.medium",
        "db.m3.large",
        "db.m3.xlarge",
        "db.m3.2xlarge",
        "db.m4.large",
        "db.m4.xlarge",
        "db.m4.2xlarge",
        "db.m4.4xlarge",
        "db.m4.10xlarge",
        "db.r3.large",
        "db.r3.xlarge",
        "db.r3.2xlarge",
        "db.r3.4xlarge",
        "db.r3.8xlarge",
        "db.m2.xlarge",
        "db.m2.2xlarge",
        "db.m2.4xlarge",
        "db.cr1.8xlarge",
        "db.t2.micro",
        "db.t2.small",
        "db.t2.medium",
        "db.t2.large"
    ]
))

db_multi_az = t.add_parameter(Parameter(
    "MultiAZDatabase",
    Description="Create a Multi-AZ PostgreSQL Amazon RDS database instance",
    Type="String",
    ConstraintDescription="must be either true or false.",
    Default="false",
    AllowedValues=[
        "true",
        "false"
      ]
))


rabbit_instance_class = t.add_parameter(Parameter(
    "RabbitInstanceClass",
    Default="t2.small",
    Description="RabbitMQ EC2 instance type",
    Type="String",
    ConstraintDescription="must be a valid EC2 instance type.",
    AllowedValues=[
        "t1.micro",
        "t2.nano",
        "t2.micro",
        "t2.small",
        "t2.medium",
        "t2.large",
        "m1.small",
        "m1.medium",
        "m1.large",
        "m1.xlarge",
        "m2.xlarge",
        "m2.2xlarge",
        "m2.4xlarge",
        "m3.medium",
        "m3.large",
        "m3.xlarge",
        "m3.2xlarge",
        "m4.large",
        "m4.xlarge",
        "m4.2xlarge",
        "m4.4xlarge",
        "m4.10xlarge",
        "c1.medium",
        "c1.xlarge",
        "c3.large",
        "c3.xlarge",
        "c3.2xlarge",
        "c3.4xlarge",
        "c3.8xlarge",
        "c4.large",
        "c4.xlarge",
        "c4.2xlarge",
        "c4.4xlarge",
        "c4.8xlarge",
        "g2.2xlarge",
        "g2.8xlarge",
        "r3.large",
        "r3.xlarge",
        "r3.2xlarge",
        "r3.4xlarge",
        "r3.8xlarge",
        "i2.xlarge",
        "i2.2xlarge",
        "i2.4xlarge",
        "i2.8xlarge",
        "d2.xlarge",
        "d2.2xlarge",
        "d2.4xlarge",
        "d2.8xlarge",
        "hi1.4xlarge",
        "hs1.8xlarge",
        "cr1.8xlarge",
        "cc2.8xlarge",
        "cg1.4xlarge"
      ]
))


environment = t.add_parameter(Parameter(
    "Environment",
    Description="Stack environment (e.g. prod, dev, int)",
    Type="String",
    MinLength="1",
    MaxLength="12",
    Default="dev",
))


db_sg = t.add_resource(SecurityGroup(
    "DBSecurityGroup",
    GroupDescription="Client access.",
    VpcId=Ref(vpc_id),
    SecurityGroupIngress=[
        SecurityGroupRule("WebAppAccess",
                          SourceSecurityGroupId=Ref(webserver_sg),
                          ToPort="5432",
                          FromPort="5432",
                          IpProtocol="tcp"),
        SecurityGroupRule("TylerAccess", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="73.173.214.176/32"),
        SecurityGroupRule("JoeAccess", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="65.254.97.100/32"),
        SecurityGroupRule("JoeAccess2", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="108.66.75.162/32"),
        SecurityGroupRule("JoeAccess3", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="71.86.4.190/32"),
        SecurityGroupRule("JoeAccess4", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="75.133.14.178/32"),
        SecurityGroupRule("JoeAccess4", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="54.87.125.141/32"),
        SecurityGroupRule("JoeAccess4", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="54.167.99.192/32"),
        SecurityGroupRule("JoeAccess4", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="52.205.224.226/32"),
        SecurityGroupRule("JoeAccess4", IpProtocol="tcp", FromPort="5432", ToPort="5432", CidrIp="52.206.122.170/32")
    ]
))


db = t.add_resource(DBInstance(
    "db",
    AllocatedStorage=Ref(db_storage),
    DBInstanceClass=Ref(db_instance_class),
    Engine="postgres",
    MasterUsername=Ref(db_user),
    MasterUserPassword=Ref(db_password),
    VPCSecurityGroups=[Ref(db_sg)]
))

rabbit_mq_sg = t.add_resource(SecurityGroup(
    "RabbitMQ",
    GroupDescription="rabbitmq-sg-ingress",
    SecurityGroupIngress=[
        SecurityGroupRule("JenkinsAccess", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="54.173.150.226/32"),
        SecurityGroupRule("TylerAccess", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="73.173.214.176/32"),
        SecurityGroupRule("JoeAccess", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="65.254.97.100/32"),
        SecurityGroupRule("JoeAccess2", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="108.66.75.162/32"),
        SecurityGroupRule("JoeAccess3", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="71.86.4.190/32"),
        SecurityGroupRule("JoeAccess4", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="75.133.14.178/32"),
        SecurityGroupRule("SontagAccess", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="47.215.167.239/32"),
        SecurityGroupRule("RabbitMQWeb", IpProtocol="tcp", FromPort="15672", ToPort="15672", CidrIp="69.255.184.149/32"),
        SecurityGroupRule("RabbitMQ", IpProtocol="tcp", FromPort="5672", ToPort="5672", CidrIp="69.255.184.149/32"),
        SecurityGroupRule("ClientAccess", IpProtocol="tcp", FromPort="5672", ToPort="5672", SourceSecurityGroupId=Ref(webserver_sg))
    ],
))

ec2_instance = t.add_resource(Instance(
    "Ec2Instance",
    ImageId=base_ami,
    InstanceType=Ref(rabbit_instance_class),
    KeyName=Ref(key_name),
    SecurityGroups=[Ref(rabbit_mq_sg)],
    Tags=[{'Key': 'Name', 'Value': Join('-', ['rabbitmq', Ref(environment)])}]
))

eip = t.add_resource(EIP(
    "RabbitMQEIP",
    InstanceId=Ref(ec2_instance),
    Domain="vpc"
))

static_bucket = t.add_resource(Bucket("StaticBucket",
                       BucketName=Join('-', ['firecares', Ref(environment), 'static']),
                       AccessControl=PublicRead,
                       CorsConfiguration=CorsConfiguration(CorsRules=[CorsRules(AllowedOrigins=Ref(s3_static_allowed_cors_origin), AllowedMethods=['GET', 'HEAD'])])
                       ))

document_upload_bucket = t.add_resource(Bucket("DocumentUploadBucket",
                                BucketName=Join('-', ['firecares', Ref(environment), 'uploads']),
                                AccessControl=PublicRead))


t.add_output([
    Output(
        "RabbitMQIP",
        Description="RabbitMQ's Elastic IP",
        Value=Ref(eip),
    )
])

t.add_output([
    Output(
        "WebServerSecurityGroup",
        Description="WebserverSecurityGroup",
        Value=Ref(webserver_sg),
    )
])


if __name__ == '__main__':
    print t.to_json()
