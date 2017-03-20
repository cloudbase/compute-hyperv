# Copyright 2014 Cloudbase Solutions Srl
#
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import mock
from os_win import utilsfactory

from hyperv.nova import vmops
from hyperv.tests import test


class HyperVBaseTestCase(test.NoDBTestCase):
    def setUp(self):
        super(HyperVBaseTestCase, self).setUp()

        utilsfactory_patcher = mock.patch.object(utilsfactory, '_get_class')
        utilsfactory_patcher.start()
        self.addCleanup(utilsfactory_patcher.stop)

    def _lazy_patch_autospec_class(self, *class_types):
        for class_type in class_types:
            # we're patching the class itself, so its return_value should be
            # a lazy mock.
            lazy_mock = mock.Mock(spec=class_type)
            patcher = mock.patch(
                '.'.join([class_type.__module__, class_type.__name__]),
                mock.Mock(return_value=lazy_mock))
            patcher.start()
            self.addCleanup(patcher.stop)


class MockSpecTestCase(HyperVBaseTestCase):

    def test_spec(self):
        self._lazy_patch_autospec_class(vmops.VMOps)
        ops = vmops.VMOps()

        ops.get_info(mock.sentinel.instance)
        ops.get_info.assert_called_once_with(mock.sentinel.instance)

        self.assertRaises(TypeError, ops.get_info)
        self.assertRaises(TypeError, ops.get_info, mock.sentinel.foo,
                          mock.sentinel.lish)
        self.assertRaises(AttributeError, getattr, ops, 'nope')
