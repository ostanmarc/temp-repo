import os
import boto3
import uuid
import logging

from jinja2 import Template


AWS_REGION = 'us-west-2'

logging.basicConfig()
logger = logging.getLogger('autoproxy-generate')
logger.setLevel(logging.DEBUG)


class PeeringRecord(object):

    def __init__(self, dns_zone_name):
        self.friendly_name = dns_zone_name.strip('.').replace('.', '_')
        self.dns_zone_name = dns_zone_name.rstrip('.')

        self.wildcard = None
        self.ingress = None
        self.api = None
        self.proxy = None

    def add_record(self, record):
        # route53 returns a funky octal encoded asterisk
        record = record.replace('\\052', '*').strip('.')
        if record == '*.int.' + self.dns_zone_name:
            self.wildcard = record.replace('*', '')  # remove the *
        elif record == 'ingress-int.' + self.dns_zone_name:
            self.ingress = record
        elif record == 'api.' + self.dns_zone_name:
            self.api = record
        elif record == 'proxy.api.' + self.dns_zone_name:
            self.proxy = record
        elif record == 'proxy.api.k8s.' + self.dns_zone_name:
            self.proxy = record
        elif record == 'api.k8s.' + self.dns_zone_name:
            self.api = record

    @property
    def create_api_proxy(self):
        if self.proxy and self.api:
            return True
        return False

    def as_dict(self):
        return dict(
            dns_zone_name=self.dns_zone_name,
            friendly_name=self.friendly_name,
            wildcard=self.wildcard,
            ingress=self.ingress,
            api=self.api,
            proxy=self.proxy,
            create_api_proxy=self.create_api_proxy,
            )


def session_for_role(role_arn):
    sts = boto3.client('sts', region_name=AWS_REGION)
    role = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName='auto-peering-proxy-{}'.format(uuid.uuid4().hex),
        )
    creds = role['Credentials']
    return boto3.session.Session(
        region_name=AWS_REGION,
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        )


def in_desired_region(route53, hosted_zone, tools_vpc_ids, desired_region):
    if desired_region is not None:
        vpcs = route53.get_hosted_zone(Id=hosted_zone['Id'])['VPCs']

        for vpc in vpcs:
            region = vpc['VPCRegion']
            if (vpc['VPCId'] in tools_vpc_ids and region == desired_region) or region == desired_region:
                return True

        return False
    else:
        return True


def fetch_hosted_zones(route53, tools_vpc_ids, desired_region):
    response = route53.list_hosted_zones()
    logger.debug("considering hosted zones to process: %s", response)
    hosted_zones = []
    # Assume there's no need to peer to the tools VPC because of e.g. a VPN
    # connection.  So, skip hosted zones associated with it.
    zones_to_ignore = [ 'tools.kube.llabs.io.' ]
    for hosted_zone in response['HostedZones']:
        if not hosted_zone['Config']['PrivateZone']:
            logger.debug('Hosted zone is not private. Skipping %s',
                         hosted_zone['Name'])
            continue
        if hosted_zone['Name'] in zones_to_ignore:
            logger.debug('skipping hosted zone %s', hosted_zone['Name'])
            continue
        if not in_desired_region(route53, hosted_zone, tools_vpc_ids, desired_region):
            continue

        hosted_zones.append(hosted_zone)
    return hosted_zones


def fetch_peering_records(session, tools_vpc_ids, desired_region):
    route53 = session.client('route53', region_name=AWS_REGION)
    hosted_zones = fetch_hosted_zones(route53, tools_vpc_ids, desired_region)
    peering_records = []

    for hosted_zone in hosted_zones:
        logger.debug('Looking for records in %s', hosted_zone['Name'])
        peering_record = PeeringRecord(hosted_zone['Name'])

        record_set_response = route53.list_resource_record_sets(
            HostedZoneId=hosted_zone['Id'],
        )
        for record_set in record_set_response['ResourceRecordSets']:
            # We don't care about anything other than A and CNAMEs
            if record_set['Type'] not in ('A', 'CNAME',):
                continue
            peering_record.add_record(record_set['Name'])
        peering_records.append(peering_record.as_dict())
    return peering_records


def generate_haproxy_config(peering_records, dns_ips, github=True):
    path = os.path.join(os.path.dirname(__file__), 'haproxy.cfg.template')
    template = Template(open(path).read())
    output = template.render({'peering_records': peering_records, 'dns_ips': dns_ips, 'github': github})
    logger.debug('Rendered config\n%s', output)
    return output


def upload_proxy_config(session, s3_bucket, s3_key, proxy_config):
    s3 = session.resource('s3')
    bucket = s3.Bucket(s3_bucket)
    # write the proxy config to a tmp file since
    # boto3 has issues with file-likes
    # https://github.com/boto/s3transfer/issues/80
    with open('tmp.haproxy.config', 'w') as fd:
        fd.write(proxy_config)

    # And upload it.
    with open('tmp.haproxy.config') as config:
        bucket.upload_fileobj(config, s3_key)


def generate(role_arns, s3_role_arn, s3_bucket, s3_key, tools_vpc_ids, desired_region, dns_ips, dry_run):
    sessions = [session_for_role(arn) for arn in role_arns]
    # collect all the dns records that we want to expose through
    # the peering proxy.
    peering_records = []
    for session in sessions:
        peering_records.extend(fetch_peering_records(session, tools_vpc_ids, desired_region))

    # generate haproxy config
    github = desired_region is None
    haproxy_config = generate_haproxy_config(peering_records, dns_ips, github)

    # upload to s3
    if not dry_run:
        tools_session = session_for_role(s3_role_arn)
        upload_proxy_config(tools_session, s3_bucket, s3_key, haproxy_config)


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--account-role-arns',
        nargs='+',
        help='''List of account role arns to use to lookup dns records.''',
        default=[
            'arn:aws:iam::963533716458:role/terraform', # test
            'arn:aws:iam::790169481217:role/terraform', # prod
            'arn:aws:iam::240321752838:role/terraform', # tools
            ],
    )
    parser.add_argument(
        '--s3-role-arn',
        help='''Role ARN for the account where the s3 bucket lives.''',
        default='arn:aws:iam::240321752838:role/terraform',
    )
    parser.add_argument(
        '--s3-bucket-name',
        default='llabs-peering-proxy',
    )
    parser.add_argument(
        '--s3-bucket-key',
        required=True
    )

    parser.add_argument(
        '--desired-region',
    )

    parser.add_argument(
        '--tools-vpc-ids',
        default='vpc-f04aac96,vpc-08ac94feff694074c'
    )

    parser.add_argument(
        '--dns-ips',
        required=True
    )

    parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                        help='generate the haproxy config, but don\'t publish')

    args = parser.parse_args()
    generate(args.account_role_arns,
             args.s3_role_arn,
             args.s3_bucket_name,
             args.s3_bucket_key,
             args.tools_vpc_ids.split(','),
             args.desired_region,
             args.dns_ips.split(','),
             args.dry_run)


if __name__ == '__main__':
    main()
