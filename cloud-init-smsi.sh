#!/bin/bash

export DEBIAN_FRONTEND=noninteractive
apt-get update

apt-get -y --force-yes install software-properties-common
add-apt-repository ppa:vbernat/haproxy-1.7

apt-get update
apt-get -y --force-yes install haproxy

apt-get -y --force-yes install git

echo "$(getent hosts peering-proxy-us-west-2.tools.llabs.io | awk '{print $1}' | head -n 1) github.int.llabs.io" >> /etc/hosts

pip install git+https://github.int.llabs.io/llabs/aws-tools.git#"subdirectory=auto-peering-proxy&egg=autoproxy"

BINPATH="$(which autoproxy-configure) --s3-config-filename haproxy-smsi.config"
LOGPATH=/var/log/autoproxy-config

touch $LOGPATH

echo "*/5 * * * * root $BINPATH >> $LOGPATH 2>&1" > /etc/cron.d/autoproxy-config

$BINPATH >> $LOGPATH 2>&1

/etc/init.d/haproxy restart
/etc/init.d/rsyslog restart
