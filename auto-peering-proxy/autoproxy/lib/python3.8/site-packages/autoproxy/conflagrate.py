import boto3
import filecmp
import logging
import shutil
import subprocess
import sys


logging.basicConfig(
    format='%(asctime)s %(levelname)-8s %(message)s',
    level=logging.INFO,
    datefmt='%Y-%m-%d %H:%M:%S')

logger = logging.getLogger('autoproxy-configure')
logger.setLevel(logging.DEBUG)

def fetch_haproxy_config(file_like, s3_bucket, s3_file):
    logger.debug('Fetching config from s3: %s/%s', s3_bucket, s3_file)
    s3 = boto3.resource('s3')
    bucket = s3.Bucket(s3_bucket)
    bucket.download_fileobj(s3_file, file_like)


def _is_valid_config(tmp_config_path, haproxy_bin_path):
    logger.debug('haproxy_bin_path: {}, tmp_config_path: {}'.format(haproxy_bin_path, tmp_config_path))
    proc = subprocess.Popen(
        ' '.join([haproxy_bin_path, '-c', '-f', tmp_config_path]),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return_code = proc.wait()
    stdout, stderr = proc.communicate()
    logger.debug('stdout: %s', stdout)
    logger.debug('stderr: %s', stderr)
    return True if return_code == 0 else False


def is_valid_config(tmp_config_path, config_path, haproxy_bin_path):
    # compare it to the existing haproxy config
    if filecmp.cmp(tmp_config_path, config_path, shallow=False):
        # if they are the same, there is no need to reconfigure.
        sys.exit('No configuration changes to apply.')
    # validate using haproxy
    return _is_valid_config(tmp_config_path, haproxy_bin_path)


def _main(tmp_config_path, config_path, s3_bucket, s3_file, reload_config, haproxy_bin_path):
    with open(tmp_config_path, 'w') as file_obj:
        # fetch config from s3
        fetch_haproxy_config(file_obj, s3_bucket, s3_file)

    if not is_valid_config(tmp_config_path, config_path, haproxy_bin_path):
        sys.exit('Configuration invalid')

    if reload_config:
        shutil.copyfileobj(open(tmp_config_path, 'r'),
                           open(config_path, 'w'))
        proc = subprocess.Popen(
            ' '.join(['/usr/sbin/service', 'haproxy', 'reload']),
            shell=True
        )
        return_code = proc.wait()
        if return_code != 0:
            sys.exit('Failed to reload haproxy.')


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--tmp-haproxy-config-path',
        default='tmp.haproxy.config',
        help='''Path to temporary haproxy config file''',
    )
    parser.add_argument(
        '--haproxy-bin-path',
        default='/usr/sbin/haproxy',
        help='''Path to haproxy executable''',
    )
    parser.add_argument(
        '--haproxy-config-path',
        default='/etc/haproxy/haproxy.cfg',
        help='''Path to haproxy config file on peering proxy host.''',
    )
    parser.add_argument(
        '--s3-config-bucket',
        default='llabs-peering-proxy',
        help='''S3 bucket which contains the haproxy config file''',
    )
    parser.add_argument(
        '--s3-config-filename',
        default='haproxy.config',
        help='''Filename of haproxy config stored in S3 bucket.''',
    )
    parser.add_argument(
        '--no-reload',
        action='store_true',
        help='''Don't reload haproxy''',
    )

    args = parser.parse_args()
    _main(args.tmp_haproxy_config_path,
         args.haproxy_config_path,
         args.s3_config_bucket,
         args.s3_config_filename,
         not args.no_reload,
          args.haproxy_bin_path)


if __name__ == '__main__':
    main()
