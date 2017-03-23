from datetime import datetime
from pytz import timezone
from troposphere import Ref, Template, Parameter, GetAZs, Output, Join, GetAtt
from troposphere.autoscaling import LaunchConfiguration, AutoScalingGroup, Tag
from troposphere.ec2 import Instance, SecurityGroup, SecurityGroupRule
from troposphere.elasticloadbalancing import LoadBalancer, AccessLoggingPolicy
from troposphere.rds import DBInstance, DBParameterGroup, DBSecurityGroup, DBSecurityGroupIngress, RDSSecurityGroup
from troposphere.s3 import Bucket, PublicRead
from troposphere.route53 import RecordSetType

t = Template()
t.add_description("Create FireCARES Webserver Load Balancer and Auto-Scaling group")

base_ami = "ami-7646e460"

now = datetime.utcnow().replace(tzinfo=timezone('UTC')).isoformat()

key_name = t.add_parameter(Parameter(
    "KeyName",
    Description="Name of an existing EC2 KeyPair to enable SSH access to the instances",
    Type="AWS::EC2::KeyPair::KeyName",
    ConstraintDescription="Must be the name of an existing EC2 KeyPair."
))

ami = t.add_parameter(Parameter(
    "baseAmi",
    Description="Name of the AMI to use",
    Type="String",
    ConstraintDescription="Must be the name of an existing AMI.",
    Default=base_ami
))

web_capacity = t.add_parameter(Parameter(
    "WebServerCapacity",
    Default="2",
    Description="The initial number of WebServer instances",
    Type="Number",
    ConstraintDescription="must be between 1 and 5 EC2 instances.",
    MinValue="1",
    MaxValue="5",
))

commit = t.add_parameter(Parameter(
    "CommitHash",
    Description="Commit hash used for building the web VM",
    Type="String"
))

web_instance_class = t.add_parameter(Parameter(
    "WebInstanceClass",
    Default="t2.medium",
    Description="WebServer EC2 instance type",
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

load_balancer = t.add_resource(LoadBalancer(
    "LoadBalancer",
    CrossZone=True,
    AvailabilityZones=GetAZs(""),
    LoadBalancerName=Join('-', ['firecares', Ref(environment), Ref(commit)]),
    LBCookieStickinessPolicy=[
      {
        "PolicyName": "CookieBasedPolicy",
        "CookieExpirationPeriod": "30"
      }
    ],
    Listeners=[
     {
        "LoadBalancerPort": "80",
        "InstancePort": "80",
        "Protocol": "HTTP",
        "PolicyNames": [
          "CookieBasedPolicy"
        ]
      },
     {
        "LoadBalancerPort": "443",
        "InstancePort": "80",
        "Protocol": "HTTPS",
        "SSLCertificateId": "arn:aws:iam::164077527722:server-certificate/firecares"
      }
    ]
))

web_sg = t.add_resource(SecurityGroup(
    "WebServers",
    GroupDescription=Join(' - ', ["FireCARES webserver group", Ref(environment), Ref(commit)]),
    SecurityGroupIngress=[
        SecurityGroupRule("ELBAccess",
                          IpProtocol="tcp",
                          FromPort="80",
                          ToPort="80",
                          SourceSecurityGroupOwnerId=GetAtt(load_balancer, "SourceSecurityGroup.OwnerAlias"),
                          SourceSecurityGroupName=GetAtt(load_balancer, "SourceSecurityGroup.GroupName")
                          ),
        SecurityGroupRule("JenkinsAccess", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="54.173.150.226/32"),
        SecurityGroupRule("TylerAccess", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="69.255.184.149/32"),
        SecurityGroupRule("JoeAccess", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="65.254.97.100/32"),
        SecurityGroupRule("JoeAccess2", IpProtocol="tcp", FromPort="22", ToPort="22", CidrIp="108.66.75.162/32")
        ],
    ))


launch_configuration = t.add_resource(LaunchConfiguration(
    "WebServerLaunchConfiguration",
    ImageId=Ref(ami),
    InstanceType=Ref(web_instance_class),
    KeyName=Ref(key_name),
    SecurityGroups=[Ref(web_sg)]
    # SecurityGroups=['sg-6774931c', 'sg-3674934d', 'sg-5f749324'],
    # ClassicLinkVPCId='vpc-bb3cd6dc'
))

autoscaling_group = t.add_resource(AutoScalingGroup(
    "WebserverAutoScale",
    AvailabilityZones=['us-east-1b', 'us-east-1c'],
    DesiredCapacity=Ref(web_capacity),
    MinSize="1",
    MaxSize="5",
    Tags=[
        Tag("environment", Ref(environment), True),
        Tag("Name", Join('-', ['web-server', Ref(environment), Ref(commit)]), True),
        Tag("Group", Join('-', ['web-server', Ref(environment)]), True)
    ],
    LoadBalancerNames=[Ref(load_balancer)],
    HealthCheckType="EC2",
    LaunchConfigurationName=Ref(launch_configuration)
))

t.add_output([
    Output(
        "stackURL",
        Description="Stack url",
        Value=Join("", [GetAtt(load_balancer, 'DNSName')]),
    )
])

t.add_output([
    Output(
        "WebServerSecurityGroup",
        Description="Web server security group.",
        Value=Join("", [GetAtt(web_sg, 'GroupId')]),
    )
])

t.add_output([
    Output(
        "AMI",
        Description="Web server ami image group.",
        Value=Ref(ami),
    )
])

if __name__ == '__main__':
    print t.to_json()
