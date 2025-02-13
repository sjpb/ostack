# ostack

CLI tool for openstack. Primarily focussed on providing more useful listings
for developers than given by
[OpenStackClient](https://docs.openstack.org/python-openstackclient/latest/).

Currently it only supports a subset of resources. This list describes the benefits
of the default view compared to OpenStackClient:
- `baremetal-node`: Shows the resource class by default
- `image`: Shows disk format, size and visibility by default
- `port`: Shows the attached instance, network name, vnic type and security group IDs by default
- `network`: Currently the same
- `project`: Shows which project is "active", i.e. your creds are for
- `server`: Shows the Nova host the instance is on (subject to permissions/policy)
- `volume`: ?

It can provide json output via `-f --format` option to `ostack`.

The `ostack * list` command provides useful filtering and output options:
    `--match, -m FIELD=VALUE`: Show only matches FIELD=VALUE where VALUE in
    FIELD (case-insensitive). Can be given multiple times.
    `--sort, -s FIELD`: Sort output by FIELD
    `--columns, -c FIELD1[,FIELD2,...]`: Show comma-separated fields
