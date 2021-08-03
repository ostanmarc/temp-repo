#!/bin/bash

virtualenv autoproxy
source autoproxy/bin/activate

pip install --upgrade .

autoproxy-generate --dns-ips "10.110.133.4,10.110.134.4,10.110.135.4" --s3-bucket-key haproxy.config $@
autoproxy-generate --dns-ips "10.110.185.75,10.110.186.97,10.110.187.19" --desired-region eu-central-1 --s3-bucket-key haproxy-eu-central-1.config $@
