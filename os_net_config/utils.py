# -*- coding: utf-8 -*-

# Copyright 2014 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import glob
import logging
import os
import re
import yaml
import objects
from string import Template


logger = logging.getLogger(__name__)
_SYS_CLASS_NET = '/sys/class/net'


def write_config(filename, data):
    with open(filename, 'w') as f:
        f.write(str(data))


def get_file_data(filename):
    if not os.path.exists(filename):
        return ''

    try:
        with open(filename, 'r') as f:
            return f.read()
    except IOError:
        logger.error("Error reading file: %s" % filename)
        return ''


def interface_mac(name):
    try:
        with open('/sys/class/net/%s/address' % name, 'r') as f:
            return f.read().rstrip()
    except IOError:
        logger.error("Unable to read mac address: %s" % name)
        raise


def _is_active_nic(interface_name):
    try:
        if interface_name == 'lo':
            return False

        addr_assign_type = None
        with open(_SYS_CLASS_NET + '/%s/addr_assign_type' % interface_name,
                  'r') as f:
            addr_assign_type = int(f.read().rstrip())

        carrier = None
        with open(_SYS_CLASS_NET + '/%s/carrier' % interface_name, 'r') as f:
            carrier = int(f.read().rstrip())

        address = None
        with open(_SYS_CLASS_NET + '/%s/address' % interface_name, 'r') as f:
            address = f.read().rstrip()

        if addr_assign_type == 0 and carrier == 1 and address:
            return True
        else:
            return False
    except IOError:
        return False


def ordered_active_nics():
    embedded_nics = []
    nics = []
    for name in glob.iglob(_SYS_CLASS_NET + '/*'):
        nic = name[(len(_SYS_CLASS_NET) + 1):]
        if _is_active_nic(nic):
            if nic.startswith('em') or nic.startswith('eth'):
                embedded_nics.append(nic)
            else:
                nics.append(nic)
    return sorted(embedded_nics) + sorted(nics)


def diff(filename, data):
    file_data = get_file_data(filename)
    logger.debug("Diff file data:\n%s" % file_data)
    logger.debug("Diff data:\n%s" % data)
    # convert to string as JSON may have unicode in it
    return not file_data == data


def tokenize_template(template):
    """Extract out the tokens from a yaml template

    :param template: The os-net-config template with tokens to be replaced
    :return list: Returns a list of the tokens in the template
    """
    token = re.compile('\$\{.*\}')
    token_match = token.findall(template)
    logger.debug('Tokens matched: %s' % token_match)
    return token_match


def process_template(template, replacements):
    """Perform string.template substitution based on the replacement dict.

    :param template: The raw template with tokens to be replaced.
    :param replacements: A dict of tokens with replacement values
    :return config: The raw os-net-config.yaml produced from the template.
    """
    template_obj = Template(template)
    return template_obj.safe_substitute(replacements)


def token_query(subnet, token_keys, ip_index):
    if token_keys[1] == "address":
        if ip_index:
            return subnet.address(int(ip_index))
        else:
            raise IndexError("Cannot assign address without ip_index in yaml.")
    elif (token_keys[1] == "ip") and (token_keys[2] == "netmask"):
        return getattr(subnet, token_keys[1] + '_' + token_keys[2])
    else:
        return getattr(subnet, token_keys[1].strip())


def replace_token(subnets, token_keys, ip_index):
    """Replace field token with value

    :param subnets: List of subnet objects to use for replacement
    :param token_keys: List of the token split by underscores
    :return: replacement
    """
    token_keys_ip = False
    if len(token_keys) > 5:
        # Subnet referenced in the form IP10_0_0_0_8 rather than by name
        subnet_ref = token_keys[0].strip('IP') + '.'
        subnet_ref += '.'.join(token_keys[1:4]) + '/' + token_keys[4]
        token_keys_ip = token_keys
        token_keys = [subnet_ref]
        for token in token_keys_ip[5:]:
            token_keys.append(token)

    for subnet in subnets:
        if (token_keys[0] == subnet.name) or\
                (token_keys[0] == subnet.ip_netmask):
            return token_query(subnet, token_keys, ip_index)
    if token_keys_ip:
        # Subnet referenced not found, create subnet and process query
        new_subnet = objects.Subnet(subnet_ref, name="")
        return token_query(new_subnet, token_keys, ip_index)


def replace_tokens(network_config, ip_index):
    """ Replace tokens in a network_config with the replacement values

    :param network_config: raw network_config yaml (may contain tokens)
    :param subnets: array of subnets defined from subnets yaml in config
    :param index: <subnet>_address returns the Nth address according to index
    :return: rendered_config: network_config with tokens replaced
    """

    subnets_array = yaml.load(network_config).get("subnets")
    subnets = []
    # Create subnets
    for subnet in subnets_array:
        subnet_name = ""
        kwargs = {}
        if "name" in subnet:
            subnet_name = subnet["name"]
        if "gateway" in subnet:
            kwargs["gateway"] = subnet["gateway"]
        if "host_ip_range" in subnet:
            kwargs["host_ip_range"] = subnet["host_ip_range"]
        logger.info('Creating subnet "%s" with parameters: %s' %
                    (subnet_name, kwargs))
        obj = objects.Subnet(subnet["ip_netmask"], subnet_name, **kwargs)
        subnets.append(obj)
    for subnet in subnets:
        logger.debug('Subnets created from config file:')
        logger.debug('Subnet created: "%s": %s' %
                     (subnet.name, repr(subnet.network)))
    # replace tokens (if any) in network_config
    replacements = {}
    token_match = tokenize_template(network_config)
    for token in token_match:
        token_raw = token.strip("$|{|}")
        token_keys = token_raw.split('_')
        for i in range(0, len(token_keys)):
            token_keys[i] = token_keys[i].strip()
        replacements[token_raw] = replace_token(subnets, token_keys, ip_index)
    logger.debug('Field token replacements: %s' % replacements)
    if replacements:
        rendered_config = process_template(network_config, replacements)
        return rendered_config
    else:
        return network_config
