#!/usr/bin/env python3
""" OpenStack CLI supporting selections, sorting and bulk operations """

import argparse, pprint, json, operator, sys, collections
from tabulate import tabulate
import openstack

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-f', '--format', choices=['table', 'json'], default='table', help='output format')
parser_sub = parser.add_subparsers(dest='object', help='OpenStack object')

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
def debug(s):
    return str(s.to_dict())

# --

class OsCmd:
    def __init__(self, cmd, proxy, list_func, fields, list_requires=None):
        self.cmd = cmd
        self.proxy = proxy
        self.list_func = list_func
        self.fields = fields
        self.list_requires = list_requires or []
    
    def list(self, conn):
        """ return a dict of objects keyed by ID """
        proxy = getattr(conn, self.proxy)
        resources = getattr(proxy, os_cmd.list_func)(details=True)
        return dict((r.id, r) for r in resources)
    
    # def format(self):

class ByID:
    def __init__(self, source_field, resource_type, resource_field):
        """ source_field: field of current resource - is assumed to have an 'id' key
            resource_type: the type of resource to use
            resource_field: the field in the resource to return
        """
        self.source_field = source_field
        self.resource_type = resource_type
        self.resource_field = resource_field
        
    def __call__(self, resources, current_resource):
        # print(len(resources[self.resource_type]))
        target_resource_id =current_resource[self.source_field]['id']
        if target_resource_id is None:
            return None
        target_resource = resources[self.resource_type][target_resource_id] # TODO:handle error here
        return target_resource[self.resource_field]

OS_CMDS = {
    'server':OsCmd(
        cmd='server',
        proxy='compute',
        list_func='servers',
        fields={'name':str, 'image_name':ByID('image', 'image', 'name'), 'status': str, 'addresses':addresses, 'flavor':name, 'compute_host':str, 'id':str},
        list_requires=['image'],
        ),
    'image': OsCmd('image', 'image', 'images', {'name':str, 'disk_format':str, 'size':bytes, 'visibility':str, 'id':str}),
    'port': OsCmd('port', 'network', 'ports', {'name':str, 'network_id':str, 'device_owner':str, 'device_id':str, 'binding_vnic_type':str})
}

for object, cmd in OS_CMDS.items():
    object_parser = parser_sub.add_parser(object)
    parser_sub_sub = object_parser.add_subparsers(dest='action', help='action to take')
    list_parser = parser_sub_sub.add_parser('list')
    list_parser.add_argument('--match', '-m', help='Show only matches k=v where v in k', action='append')
    list_parser.add_argument('-s', '--sort', help='sort output by field')

    delete_parser = parser_sub_sub.add_parser('delete')
    delete_parser.add_argument('target', help="id, comma-separated list of ids, or list of json objects with 'id' attribute")

if __name__ == '__main__':
    args = parser.parse_args()
    # print(args)
    # exit()
    
    matchers = dict(v.split('=') for v in args.match) if args.match else {}
    conn = openstack.connection.from_config()
    user_os_cmd = OS_CMDS[args.object]
    
    if args.action == 'list':
        
        # collect resources:
        resources = {}
        all_os_cmds = [user_os_cmd] + [OS_CMDS[n] for n in user_os_cmd.list_requires]
        for os_cmd in all_os_cmds:
            resources[os_cmd.cmd] = os_cmd.list(conn)
        
        # format/expand the user command resources:
        outputs = []
        for id, resource in resources[user_os_cmd.cmd].items():
            resource_dict = {}
            for field, formatter in user_os_cmd.fields.items():
                if isinstance(formatter, ByID):
                    resource_dict[field] = formatter(resources, resource)
                else:
                    resource_dict[field] = formatter(resource[field])
            
            for k, v in matchers.items():
                if v.lower() not in resource_dict[k].lower():
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

    # elif args.action == 'delete':
    #     if args.target == '-': # read json from stdin
    #         targets_json = json.loads(sys.stdin.read())
    #         for t in targets_json:
    #             print(t['id'], t['name'])
    #         targets = [t['id'] for t in target_json]
    #     else:
    #         # TODO: currently these must be IDs, consider coping with names?
    #         targets = args.target.split(',')
    #         for t in targets:
    #             print(t)
    #     # TODO: fixme for using sys.stdin too?
    #     # ui = input(f'Confirm deletion of {len(targets)} resources:?')
    #     for t in targets:
    #         conn.compute.delete_server(t)
    