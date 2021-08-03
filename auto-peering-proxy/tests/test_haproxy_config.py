import os
import tempfile
import boto3

from moto import mock_s3
from StringIO import StringIO
from autoproxy import conflagrate, generate


FIXTURE_PATH = os.path.join(os.path.dirname(__file__), 'fixtures')


def fixture_path(name):
    return os.path.join(FIXTURE_PATH, name)


@mock_s3
def test_fetch_file():
    s3_bucket = 'my_bucket'
    s3_file = 'my_file'

    s3 = boto3.resource('s3')
    bucket = s3.Bucket(s3_bucket)
    bucket.create()

    # TODO After the following issue is resolved.
    # We use this fixture file to mock upload the resource
    # because https://github.com/boto/s3transfer/issues/80
    with open(fixture_path('test_haproxy.config')) as file_obj:
        bucket.upload_fileobj(file_obj, s3_file)

    buf = StringIO()
    conflagrate.fetch_haproxy_config(buf, s3_bucket, s3_file)
    assert 'localhost' in buf.getvalue()


def test_is_valid_config():
    # these two are the same
    assert not conflagrate.is_valid_config(
        fixture_path('test_haproxy.config'),
        fixture_path('test_valid_haproxy.config')
        )

    assert conflagrate.is_valid_config(
        fixture_path('test_haproxy.config'),
        fixture_path('test_updated_haproxy.config')
        )

    assert conflagrate._is_valid_config(
        fixture_path('test_haproxy.config'))
    assert not conflagrate._is_valid_config(
        fixture_path('test_invalid_haproxy.config'))


def test_peering_record():
    # hosted zone domain names contain a trailing '.'
    dns_zone_name = 'foo.bar.com.'
    # We remove it to make it friendly to haproxy config
    expected_zone_name = 'foo.bar.com'

    peering_record = generate.PeeringRecord(dns_zone_name)

    assert peering_record.dns_zone_name == expected_zone_name

    wildcard_record = '\\052.int.foo.bar.com.'
    expected_wildcard = '.int.foo.bar.com'

    peering_record.add_record(wildcard_record)

    assert peering_record.wildcard == expected_wildcard

    ingress_record = 'ingress-int.foo.bar.com.'
    expected_ingress = 'ingress-int.foo.bar.com'
    peering_record.add_record(ingress_record)

    assert peering_record.ingress ==  expected_ingress
