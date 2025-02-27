#!/usr/bin/env python3
""" OpenStack CLI supporting selections, sorting and bulk operations """

import argparse, pprint, json, operator, sys, collections
from tabulate import tabulate
import openstack

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-f', '--format', choices=['table', 'json'], default='table', help='output format')
parser_sub = parser.add_subparsers(dest='object', help='OpenStack object')

# -- formatter functions --
# There basically 3+1 types of function here, all of which are specified
# by setting a key/value in .fields, where the key is the *output* field name and
# the value is the function.
# 1. Things like addresses(): This just takes and reformats a field. The input field
#    is the same as the output field, so the key determines what gets passed to
#    the function - not necessarily a string.
# 2. Things like instance_name(): This has a property input_field set. In this
#    case this determines what field is passed as input, so this can be different
#    from the output field name.
# 3. Things like server_names_from_attachments(): This returns a function which has
#    a property is_calculated set to True. In this case the inner function is passed
#    a map `resources` an object `current_resource` and the connection object.
#    The former has keys which are resource types (e.g. "server") and values
#    are a map of resource objects keyed by id. So
#       resources[resource_type][id] -> resource object.
#    If this requires resource types which are not the current resource type,
#    list their names in `list_requires`.
# 4. lookup(): This is a generalisation of 3, for cases where the required operation
#    is to use a field in the current resource to find another resource by ID,
#    then return a field of that. TODO: be nice to provide output formatting on that.
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

def lookup(source_field, resource_type, resource_field, source_subfield=None):

    def call(resources, current_resource, conn):
        if source_subfield:
            source = current_resource.get(source_field, None)
            if source is None:
                target_resource_id is None
            else:
                target_resource_id = source.get(source_subfield, None)
        else:
            target_resource_id = current_resource.get(source_field, None)
        if target_resource_id is None:
            print(f"can't get {source_field} from {resource_type}")
            return '(unknown)'
        if target_resource_id not in resources[resource_type]:
            return '(unknown)'
        target_resource = resources[resource_type][target_resource_id] # TODO:handle error here
        return target_resource[resource_field]
    call.is_calculated = True
    return call

def display_name(s):
    return s.get('display_name', '-')

def instance_name(s): # for baremetal node
    return s.get('display_name', '-')
instance_name.input_field = 'instance_info'

def server_names_from_attachments():
    def call(resources, current_resource, conn):
        server_names = []
        for attachment in current_resource['attachments']:
            server_id = attachment['server_id']
            server_name = resources['server'][server_id]['name']
            server_names.append(server_name)
        return ','.join(server_names)
    call.is_calculated = True
    return call

def current_project():
    def call(resources, current_resource, conn):
        return '***' if current_resource.id == conn.current_project.id else ' '
    call.is_calculated = True
    return call

# --

class OsCmd:
    def __init__(self, cmd, proxy, list_func, default_fields, list_func_args=None, fields=None, list_requires=None):
        self.cmd = cmd
        self.proxy = proxy
        self.list_func = list_func
        self.list_func_args = list_func_args
        self.default_fields = default_fields
        self.fields = fields or {}
        self.list_requires = list_requires or []
    
    def list(self, conn):
        """ return a dict of objects keyed by ID """
        proxy = getattr(conn, self.proxy)
        list_func_args_evaled = self.list_func_args() if self.list_func_args is not None else []
        resources = getattr(proxy, os_cmd.list_func)(*list_func_args_evaled, details=True)
        return dict((r.id, r) for r in resources)

def delayed(str):
    """ Python string to evaluate, will have access to connection object """
    def func():
        return eval(str)
    return func

OS_CMDS = {
    'server':OsCmd(
        cmd='server', # the first cli work - ostack *server*
        proxy='compute', # conn.$PROXY - see e.g. https://docs.openstack.org/openstacksdk/latest/user/guides/compute.html#id1
        list_func='servers', # see above link example
        default_fields=('name', 'image_name', 'status', 'addresses', 'flavor', 'compute_host', 'id'),  # output fields shown by default
        fields={'image_name':lookup('image', 'image', 'name', 'id'), 'addresses':addresses, 'flavor':name}, # output fields needing formatting
        list_requires=['image'],
        ),
    'image': OsCmd(
        cmd='image',
        proxy='image',
        list_func='images',
        default_fields = ('name', 'disk_format', 'size', 'visibility', 'id'),
        fields={'size':bytes},
        ),
    'port': OsCmd(
        cmd='port',
        proxy='network',
        list_func='ports',
        default_fields=('name', 'network_name', 'device_owner', 'server_name', 'binding_vnic_type', 'id', 'security_group_ids'),
        fields={'network_name':lookup('network_id', 'network', 'name'), 'server_name':lookup('device_id', 'server', 'name')},
        list_requires=['network', 'server']
        ),
    'network': OsCmd(
        cmd='network',
        proxy='network',
        list_func='networks',
        default_fields=('name', 'id', 'subnet_ids'),
    ),
    # agh this is a pain; the command is 'baremetal node list'
    'baremetal-node': OsCmd(
        cmd='baremetal-node',
        proxy='baremetal',
        list_func='nodes',
        #default_fields=('name', 'power_state', 'provision_state', 'resource_class', 'is_maintenance', 'instance_info'),
        default_fields=('name', 'power_state', 'provision_state', 'is_maintenance', 'resource_class', 'instance_name', 'instance_image'),
        fields = {'instance_name':instance_name, 'instance_image':lookup('instance_info', 'image', 'name', 'image_source')},
        list_requires=['image'],
    ),

    'volume': OsCmd(
        cmd='volume',
        proxy='block_storage',
        list_func='volumes',
        default_fields=('id', 'name', 'status', 'size', 'volume_type', 'attached_to'),
        fields = {'attached_to':server_names_from_attachments()},
        list_requires=['server'],
    ),

    'project': OsCmd(
        cmd='project',
        proxy='identity',
        list_func='user_projects',
        list_func_args=delayed('[conn.current_user_id]'),
        default_fields = ('current', 'id', 'name'),
        fields = {'current':current_project()},
    ),

}

for object, cmd in OS_CMDS.items():
    object_parser = parser_sub.add_parser(object)
    parser_sub_sub = object_parser.add_subparsers(dest='action', help='action to take')
    list_parser = parser_sub_sub.add_parser('list')
    list_parser.add_argument('--match', '-m', help='Show only matches FIELD=VALUE where VALUE in FIELD (case-insensitive). Can be given multiple times.', action='append')
    list_parser.add_argument('-s', '--sort', help='Sort output by FIELD.', metavar='FIELD')
    list_parser.add_argument('-c', '--columns', help='Show comma-separated fields.', metavar='FIELDS')

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
        valid_fields = sorted(set(list(resources[user_os_cmd.cmd].values())[0].keys() + list(user_os_cmd.fields.keys())))
        for id, resource in resources[user_os_cmd.cmd].items():
            resource_dict = {}
            output_fields = args.columns.split(',') if args.columns else user_os_cmd.default_fields
            for field_name in output_fields:
                if field_name not in valid_fields:
                    exit(f"no column '{field_name}; valid columns are: {', '.join(valid_fields)}")
                formatter = user_os_cmd.fields.get(field_name, str)
                if getattr(formatter, 'is_calculated', False):
                    resource_dict[field_name] = formatter(resources, resource, conn)
                elif getattr(formatter, 'input_field', False):
                    resource_dict[field_name] = formatter(resource[formatter.input_field])
                else:
                    resource_dict[field_name] = formatter(resource[field_name])
                    
            
            for k, v in matchers.items():
                rval = resource_dict[k]
                if rval is None or v.lower() not in rval.lower():
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
    