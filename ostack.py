#!/usr/bin/env python3
""" OpenStack CLI supporting selections, sorting and bulk operations """

import argparse, pprint, json, operator, sys
from tabulate import tabulate
import openstack

cli = argparse.ArgumentParser(description=__doc__)
cli.add_argument('object', choices=['server'], help="object to operate on")
cli.add_argument('action', choices=['list', 'delete'], help="action to take")
cli.add_argument('target', nargs='?', default=None, help="(optional) target")
cli.add_argument('--match', '-m', help='Show only matches k=v where v in k', action='append')
cli.add_argument('-f', '--format', choices=['table', 'json'], default='table', help='output format')
cli.add_argument('-s', '--sort', help='sort output by field')

def display_server(s, fields=['name', 'status', 'id']):
    return(dict(name=s.name, status=s.status))

def addresses(s):
    # e.g. {'external': [{'version': 4, 'addr': 'x.x.x.x', 'OS-EXT-IPS:type': 'fixed', 'OS-EXT-IPS-MAC:mac_addr': 'x:x:x:x:x:x'}]}
    results = []
    for net, info in s.items():
        addrs = ','.join(p['addr'] for p in info)
        results.append(f'{net}={addrs}')
    return ','.join(results)

def name(s):
    return s['name']

DEFAULT_FIELDS = {
    ('server', 'list'): {'name':str, 'status': str, 'addresses':addresses, 'flavor':name, 'compute_host':str, 'id':str}
}

if __name__ == '__main__':
    args = cli.parse_args()
    # print(args)
    # exit()
    conn = openstack.connection.from_config()
    outputs = []
    matchers = dict(v.split('=') for v in args.match) if args.match else {}

    if args.object == 'server':
        if args.action == 'list':
            resources = conn.compute.servers(details=True)
            for r in resources:
                d = r.to_dict()
                # d = dict((k, v) for (k, v) in r.to_dict().items() if v is not None)
                # print(d)
                
                for k, v in matchers.items():
                    if v not in d[k]:
                        break
                else: # only executes if matchers DIDN'T break
                    
                    fields = DEFAULT_FIELDS[(args.object, args.action)]
                    out = dict((n, converter(d[n])) for n, converter in fields.items())
                    outputs.append(out)
                    continue
                break # only executes if matches DOES break
        if args.action == 'delete':
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
            exit() # TODO
    if args.sort:
        outputs = sorted(outputs, key=lambda d: d[args.sort])
    if args.format == 'table':
        table = tabulate(outputs, headers='keys')
        print(table)
    elif args.format == 'json':
        print(json.dumps(outputs))
