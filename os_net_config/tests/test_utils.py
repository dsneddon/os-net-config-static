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

import os.path
import shutil
import tempfile

from os_net_config.tests import base
from os_net_config import utils

_NETWORK_CONFIG1_SUBNETS = """subnets:
  -
    name: storage
    ip_netmask: 192.168.2.0/24
    gateway: 192.168.2.254
    host_ip_range: "192.168.2.10, 192.168.2.20"
"""

_NETWORK_CONFIG1 = """network_config:
    network_config:
      -
        type: interface
        name: em1
        use_dhcp: false
        addresses:
          -
            ip_netmask: ${storage_address}
        routes:
          -
            ip_netmask: 192.168.3.0/24
            gateway: ${storage_gateway}
"""

_NETWORK_CONFIG1_FINAL = """subnets:
  -
    name: storage
    ip_netmask: 192.168.2.0/24
    gateway: 192.168.2.254
    host_ip_range: "192.168.2.10, 192.168.2.20"
network_config:
    network_config:
      -
        type: interface
        name: em1
        use_dhcp: false
        addresses:
          -
            ip_netmask: 192.168.2.15/24
        routes:
          -
            ip_netmask: 192.168.3.0/24
            gateway: 192.168.2.254
"""

_NETWORK_CONFIG2_JSON = """{ "subnets": [
        {
            "ip_netmask": "192.0.2.0/24",
            "name": "tenant",
            "host_ip_range": "192.0.2.1, 192.0.2.100"
        }
   ],
  "network_config": [
        {
            "use_dhcp": True,
             "type": "interface",
             "name": "em1"
        },
        {
            "use_dhcp": False,
            "type": "interface",
            "name": "em2",
            "addresses": [
                {
                    "ip_netmask": "${tenant_address}"
                }
              ]
        }
  ]
}
"""

_NETWORK_CONFIG2_FINAL = """{ "subnets": [
        {
            "ip_netmask": "192.0.2.0/24",
            "name": "tenant",
            "host_ip_range": "192.0.2.1, 192.0.2.100"
        }
   ],
  "network_config": [
        {
            "use_dhcp": True,
             "type": "interface",
             "name": "em1"
        },
        {
            "use_dhcp": False,
            "type": "interface",
            "name": "em2",
            "addresses": [
                {
                    "ip_netmask": "192.0.2.1/24"
                }
              ]
        }
  ]
}
"""

class TestUtils(base.TestCase):

    def test_ordered_active_nics(self):

        tmpdir = tempfile.mkdtemp()
        self.stubs.Set(utils, '_SYS_CLASS_NET', tmpdir)

        def test_is_active_nic(interface_name):
            return True
        self.stubs.Set(utils, '_is_active_nic', test_is_active_nic)

        for nic in ['a1', 'em1', 'em2', 'eth2', 'z1']:
            with open(os.path.join(tmpdir, nic), 'w') as f:
                f.write(nic)

        nics = utils.ordered_active_nics()
        self.assertEqual('em1', nics[0])
        self.assertEqual('em2', nics[1])
        self.assertEqual('eth2', nics[2])
        self.assertEqual('a1', nics[3])
        self.assertEqual('z1', nics[4])

        shutil.rmtree(tmpdir)

    def test_replace_tokens_yaml(self):

        template = _NETWORK_CONFIG1_SUBNETS + _NETWORK_CONFIG1
        network_config = utils.replace_tokens(template, '5')
        self.assertEquals(_NETWORK_CONFIG1_FINAL, network_config)

    def test_replace_tokens_json(self):

        template = _NETWORK_CONFIG2_JSON
        network_config = utils.replace_tokens(template, '0')
        self.assertEquals(_NETWORK_CONFIG2_FINAL, network_config)
