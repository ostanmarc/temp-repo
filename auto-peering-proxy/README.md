# llabs auto-peering-proxy

The auto-peering-proxy is a tool used to configure the peering-proxy
(haproxy from the tools vpc to other aws accounts) without manual configuration.

There are two components:

1. autoproxy-generate: A jenkins job which generates the current haproxy
   configuration by scanning route53 hosted zones for records which match
   specific patterns.

2. autoproxy-configure: A cron job on the peering-proxy nodes that checks,
   validates, and reloads haproxy with updated configurations.


## autoproxy-generate

autoproxy-generate currently builds rules for haproxy by searching route53
accounts for private hosted zones for records which match:

a. the kubernetes api rule is created if the following matches are found:

   - `api.<hosted_zone_domain_name>` - an A record created by kops for the
     kubernetes api during cluster creation in the kuberneterizer.

   - `proxy.api.<hosted_zone_domain_name>` - a CNAME to peering-proxy.tools.llabs.io
     created by the kuberneterizer as part of cluster creation.

b. the internal ingress rule is created if the following matches are found:

   - `*.int.<hosted_zone_domain_name>` - a CNAME to peering-proxy.tools.llabs.io
     created by kuberneterizer during cluster creation. This wildcard record
     enables applications to have internal ingress access in kubernetes
     clusters without requiring records to be created in route53.

   - `ingress-int.<hosted_zone_domain_name>` - a CNAME to an A record that
     aliases to the ELB tied to an internal ingress controller created during
     cluster creation.


The haproxy config is generated on demand via a Jenkins job and stored in an
s3 bucket in the tools account.

[Tools Peering Proxy S3 Bucket](https://s3.console.aws.amazon.com/s3/buckets/llabs-peering-proxy/?region=us-east-1&tab=overview)

[Jenkins Job](https://jenkins.tools.llabs.io/job/aws-tools/job/autoproxy-generate/)


## autoproxy-configure

Installed via pip in the peering-proxy cloud-init script. autoproxy-configure is
configured to check the s3 bucket periodically to see if it has been updated.
When an updated configuration is found it validates and reloads haproxy.

[Cloud Init](https://github.int.llabs.io/llabs/aws-tools/blob/master/terraform/peering-proxy/cloud-init.sh)
