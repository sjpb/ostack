#!/usr/bin/env python3

import argparse, pprint, json, operator, sys
from tabulate import tabulate
import openstack

cli = argparse.ArgumentParser(description='List ports on a given network with instance and hypervisor information.')
cli.add_argument('object', choices=['server'])
cli.add_argument('action', choices=['list', 'delete'])
cli.add_argument('target', nargs='?', default=None)
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

DEFAULT_FIELDS = {
    ('server', 'list'): {'name':str, 'addresses':addresses, 'compute_host':str, 'id':str}
}

if __name__ == '__main__':
    args = cli.parse_args()
    # print(args)
    # exit()
    conn = openstack.connection.from_config()
    outputs = []
    matchers = dict(v.split('=') for v in args.match) if args.match else []

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
                targets = json.loads(sys.stdin.read())
            else:
                targets = args.target.split(',')
            print('\n'.join(t['name'] for t in targets))
            # TODO: fixme for using sys.stdin too?
            # ui = input(f'Confirm deletion of {len(targets)} resources:?')
            for t in targets: # TODO: need to cope with this being a name?
                print(t['id'], t['name'])
                conn.compute.delete_server(t['id'])
            exit()
    if args.sort:
        outputs = sorted(outputs, key=lambda d: d[args.sort])
    if args.format == 'table':
        table = tabulate(outputs, headers='keys')
        print(table)
    elif args.format == 'json':
        print(json.dumps(outputs))
