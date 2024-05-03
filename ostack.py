#!/usr/bin/env python3
""" OpenStack CLI supporting selections, sorting and bulk operations """

import argparse, pprint, json, operator, sys
from tabulate import tabulate
import openstack

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('object', choices=['server','image'], help="object to operate on")
cli.add_argument('action', choices=['list', 'delete'], help="action to take")
cli.add_argument('target', nargs='?', default=None, help="(optional) target")
cli.add_argument('--match', '-m', help='Show only matches k=v where v in k', action='append')
cli.add_argument('-f', '--format', choices=['table', 'json'], default='table', help='output format')
cli.add_argument('-s', '--sort', help='sort output by field')

# -- formatter functions --
def addresses(s):
    # e.g. {'external': [{'version': 4, 'addr': 'x.x.x.x', 'OS-EXT-IPS:type': 'fixed', 'OS-EXT-IPS-MAC:mac_addr': 'x:x:x:x:x:x'}]}
    results = []
    for net, info in s.items():
        addrs = ','.join(p['addr'] for p in info)
        results.append(f'{net}={addrs}')
    return ','.join(results)

def name(s):
    return s['name']

def bytes(s):
    return int(s) / (1024 * 1024)
# --

PROXIES = {
    'server': 'compute',
    'image': 'image',
}
PROXY_LIST_FUNCS = {
    'server':'servers',
    'image':'images',
}
DEFAULT_FIELDS = { # TODO: might need to split this into defaults and formatting to define formatting for non-default fields
    ('server', 'list'): {'name':str, 'status': str, 'addresses':addresses, 'flavor':name, 'compute_host':str, 'id':str},
    ('image', 'list'): {'name':str, 'disk_format':str, 'size':bytes, 'visibility':str, 'id':str}
}

if __name__ == '__main__':
    args = cli.parse_args()
    # print(args)
    # exit()
    
    matchers = dict(v.split('=') for v in args.match) if args.match else {}
    conn = openstack.connection.from_config()
    outputs = []
    
    proxy = getattr(conn, PROXIES[args.object])
    
    if args.action == 'list':
        resources = getattr(proxy, PROXY_LIST_FUNCS[args.object])(details=True)

        fields = DEFAULT_FIELDS[(args.object, args.action)]
        for r in resources:
            resource_dict = r.to_dict()
            resource_dict = dict((field, formatter(resource_dict[field])) for field, formatter in fields.items())
            for k, v in matchers.items():
                if v not in resource_dict[k]:
                    break
            else: # only executes if matchers DIDN'T break
                outputs.append(resource_dict)
                continue
        if args.sort:
            outputs = sorted(outputs, key=lambda d: d[args.sort])
        if args.format == 'table':
            table = tabulate(outputs, headers='keys')
            print(table)
        elif args.format == 'json':
            print(json.dumps(outputs, indent=2))

    elif args.action == 'delete':
        if args.target is None:
            raise ValueError('must supply target as 3rd argument')
        elif args.target == '-': # read json from stdin
            targets_json = json.loads(sys.stdin.read())
            for t in targets_json:
                print(t['id'], t['name'])
            targets = [t['id'] for t in target_json]
        else:
            # TODO: currently these must be IDs, consider coping with names?
            targets = args.target.split(',')
            for t in targets:
                print(t)
        # TODO: fixme for using sys.stdin too?
        # ui = input(f'Confirm deletion of {len(targets)} resources:?')
        for t in targets:
            conn.compute.delete_server(t)
    