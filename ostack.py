#!/usr/bin/env python3
""" OpenStack CLI supporting selections, sorting and bulk operations """

import argparse, pprint, json, operator, sys, collections
from tabulate import tabulate
import openstack

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-f', '--format', choices=['table', 'json'], default='table', help='output format')
object_parser = parser.add_subparsers(dest='object') #, help='sub-command help')

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

OsCmd = collections.namedtuple('OsCmd', ('cmd', 'proxy', 'list_func', 'fields'))

OS_CMDS = {
    'server':OsCmd('server', 'compute', 'servers', {'name':str, 'status': str, 'addresses':addresses, 'flavor':name, 'compute_host':str, 'id':str}),
    'image': OsCmd('image', 'image', 'images', {'name':str, 'disk_format':str, 'size':bytes, 'visibility':str, 'id':str})
}

for object, cmd in OS_CMDS.items():
    sub_parser = object_parser.add_parser(object)
    sub_parser.add_argument('action', choices=['list', 'delete'], help="action to take")
    sub_parser.add_argument('target', nargs='?', default=None, help="(optional) target")
    sub_parser.add_argument('--match', '-m', help='Show only matches k=v where v in k', action='append')
    sub_parser.add_argument('-s', '--sort', help='sort output by field')


if __name__ == '__main__':
    args = parser.parse_args()
    # print(args)
    # exit()
    
    # TODO: be nice to have case-insensitive matching
    matchers = dict(v.split('=') for v in args.match) if args.match else {}
    conn = openstack.connection.from_config()
    os_cmd = OS_CMDS[args.object]
    proxy = getattr(conn, os_cmd.proxy)
    if args.action == 'list':
        outputs = []
        resources = getattr(proxy, os_cmd.list_func)(details=True)

        for r in resources:
            resource_dict = r.to_dict()
            resource_dict = dict((field, formatter(resource_dict[field])) for field, formatter in os_cmd.fields.items())
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
    