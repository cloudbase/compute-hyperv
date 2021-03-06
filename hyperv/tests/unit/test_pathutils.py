#  Copyright 2014 IBM Corp.
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

import os
import time

import ddt
import mock
from nova import exception
from os_win import exceptions as os_win_exc
from six.moves import builtins

from hyperv.nova import constants
from hyperv.nova import pathutils
from hyperv.tests.unit import test_base


@ddt.ddt
class PathUtilsTestCase(test_base.HyperVBaseTestCase):
    """Unit tests for the Hyper-V PathUtils class."""

    def setUp(self):
        super(PathUtilsTestCase, self).setUp()
        self.fake_instance_dir = os.path.join('C:', 'fake_instance_dir')
        self.fake_instance_name = 'fake_instance_name'

        self._pathutils = pathutils.PathUtils()

    @ddt.data({'conf_instances_path': r'c:\inst_dir',
               'expected_dir': r'c:\inst_dir'},
              {'conf_instances_path': r'c:\inst_dir',
               'remote_server': 'fake_remote',
               'expected_dir': r'\\fake_remote\c$\inst_dir'},
              {'conf_instances_path': r'\\fake_share\fake_path',
               'remote_server': 'fake_remote',
               'expected_dir': r'\\fake_share\fake_path'},
              {'conf_instances_path_share': r'inst_share',
               'remote_server': 'fake_remote',
               'expected_dir': r'\\fake_remote\inst_share'})
    @ddt.unpack
    def test_get_instances_dir(self, expected_dir, remote_server=None,
                               conf_instances_path='',
                               conf_instances_path_share=''):
        self.flags(instances_path=conf_instances_path)
        self.flags(instances_path_share=conf_instances_path_share,
                   group='hyperv')

        instances_dir = self._pathutils.get_instances_dir(remote_server)

        self.assertEqual(expected_dir, instances_dir)

    @mock.patch.object(pathutils.PathUtils, 'get_instances_dir')
    @mock.patch.object(pathutils.PathUtils, '_check_dir')
    def test_get_instances_sub_dir(self, mock_check_dir,
                                   mock_get_instances_dir):
        fake_instances_dir = 'fake_instances_dir'
        mock_get_instances_dir.return_value = fake_instances_dir

        sub_dir = 'fake_subdir'
        expected_path = os.path.join(fake_instances_dir, sub_dir)

        path = self._pathutils._get_instances_sub_dir(
            sub_dir,
            remote_server=mock.sentinel.remote_server,
            create_dir=mock.sentinel.create_dir,
            remove_dir=mock.sentinel.remove_dir)

        self.assertEqual(expected_path, path)

        mock_get_instances_dir.assert_called_once_with(
            mock.sentinel.remote_server)
        mock_check_dir.assert_called_once_with(
            expected_path,
            create_dir=mock.sentinel.create_dir,
            remove_dir=mock.sentinel.remove_dir)

    @ddt.data({'create_dir': True, 'remove_dir': False},
              {'create_dir': False, 'remove_dir': True})
    @ddt.unpack
    @mock.patch.object(pathutils.PathUtils, 'check_create_dir')
    @mock.patch.object(pathutils.PathUtils, 'check_remove_dir')
    def test_check_dir(self, mock_check_remove_dir, mock_check_create_dir,
                       create_dir, remove_dir):
        self._pathutils._check_dir(
            mock.sentinel.dir, create_dir=create_dir, remove_dir=remove_dir)

        if create_dir:
            mock_check_create_dir.assert_called_once_with(mock.sentinel.dir)
        else:
            self.assertFalse(mock_check_create_dir.called)

        if remove_dir:
            mock_check_remove_dir.assert_called_once_with(mock.sentinel.dir)
        else:
            self.assertFalse(mock_check_remove_dir.called)

    @mock.patch.object(pathutils.PathUtils, 'check_create_dir')
    def test_check_dir_exc(self, mock_check_create_dir):

        class FakeWindowsError(Exception):
            def __init__(self, winerror=None):
                self.winerror = winerror

        mock_check_create_dir.side_effect = FakeWindowsError(
            pathutils.ERROR_INVALID_NAME)
        with mock.patch.object(builtins, 'WindowsError',
                               FakeWindowsError, create=True):
            self.assertRaises(exception.AdminRequired,
                              self._pathutils._check_dir,
                              mock.sentinel.dir_name,
                              create_dir=True)

    @ddt.data({},
              {'configured_dir_exists': True},
              {'vm_exists': True},
              {'vm_exists': True,
               'remote_server': mock.sentinel.remote_server})
    @ddt.unpack
    @mock.patch.object(pathutils.PathUtils, '_get_instances_sub_dir')
    @mock.patch.object(pathutils.PathUtils, '_get_remote_unc_path')
    @mock.patch.object(pathutils.PathUtils, '_check_dir')
    @mock.patch.object(pathutils.os.path, 'exists')
    @mock.patch('os_win.utilsfactory.get_vmutils')
    def test_get_instance_dir(self, mock_get_vmutils,
                              mock_exists,
                              mock_check_dir,
                              mock_get_remote_unc_path,
                              mock_get_instances_sub_dir,
                              configured_dir_exists=False,
                              remote_server=None, vm_exists=False):
        mock_get_instances_sub_dir.return_value = mock.sentinel.configured_dir
        mock_exists.return_value = configured_dir_exists

        expected_vmutils = (self._pathutils._vmutils
                            if not remote_server
                            else mock_get_vmutils.return_value)
        mock_get_root_dir = expected_vmutils.get_vm_config_root_dir
        mock_get_root_dir.side_effect = (
            (mock.sentinel.config_root_dir,)
            if vm_exists
            else os_win_exc.HyperVVMNotFoundException(
                vm_name=mock.sentinel.instance_name))

        mock_get_remote_unc_path.return_value = mock.sentinel.remote_root_dir

        instance_dir = self._pathutils.get_instance_dir(
            mock.sentinel.instance_name,
            remote_server=remote_server,
            create_dir=mock.sentinel.create_dir,
            remove_dir=mock.sentinel.remove_dir)

        if configured_dir_exists or not vm_exists:
            expected_instance_dir = mock.sentinel.configured_dir
        else:
            # In this case, we expect the instance location to be
            # retrieved from the vm itself.
            mock_get_root_dir.assert_called_once_with(
                mock.sentinel.instance_name)

            if remote_server:
                expected_instance_dir = mock.sentinel.remote_root_dir
                mock_get_remote_unc_path.assert_called_once_with(
                    mock.sentinel.remote_server,
                    mock.sentinel.config_root_dir)
            else:
                expected_instance_dir = mock.sentinel.config_root_dir

        self.assertEqual(expected_instance_dir, instance_dir)

        mock_get_instances_sub_dir.assert_called_once_with(
            mock.sentinel.instance_name, remote_server,
            create_dir=False, remove_dir=False)
        mock_check_dir.assert_called_once_with(
            expected_instance_dir,
            create_dir=mock.sentinel.create_dir,
            remove_dir=mock.sentinel.remove_dir)

    def _mock_lookup_configdrive_path(self, ext, rescue=False):
        self._pathutils.get_instance_dir = mock.MagicMock(
            return_value=self.fake_instance_dir)

        def mock_exists(*args, **kwargs):
            path = args[0]
            return True if path[(path.rfind('.') + 1):] == ext else False
        self._pathutils.exists = mock_exists
        configdrive_path = self._pathutils.lookup_configdrive_path(
            self.fake_instance_name, rescue)
        return configdrive_path

    def _test_lookup_configdrive_path(self, rescue=False):
        configdrive_name = 'configdrive'
        if rescue:
            configdrive_name += '-rescue'

        for format_ext in constants.DISK_FORMAT_MAP:
            configdrive_path = self._mock_lookup_configdrive_path(format_ext,
                                                                  rescue)
            expected_path = os.path.join(self.fake_instance_dir,
                                         configdrive_name + '.' + format_ext)
            self.assertEqual(expected_path, configdrive_path)

    def test_lookup_configdrive_path(self):
        self._test_lookup_configdrive_path()

    def test_lookup_rescue_configdrive_path(self):
        self._test_lookup_configdrive_path(rescue=True)

    def test_lookup_configdrive_path_non_exist(self):
        self._pathutils.get_instance_dir = mock.MagicMock(
            return_value=self.fake_instance_dir)
        self._pathutils.exists = mock.MagicMock(return_value=False)
        configdrive_path = self._pathutils.lookup_configdrive_path(
            self.fake_instance_name)
        self.assertIsNone(configdrive_path)

    def test_copy_vm_console_logs(self):
        fake_local_logs = [mock.sentinel.log_path,
                           mock.sentinel.archived_log_path]
        fake_remote_logs = [mock.sentinel.remote_log_path,
                            mock.sentinel.remote_archived_log_path]

        self._pathutils.exists = mock.Mock(return_value=True)
        self._pathutils.copy = mock.Mock()
        self._pathutils.get_vm_console_log_paths = mock.Mock(
            side_effect=[fake_local_logs, fake_remote_logs])

        self._pathutils.copy_vm_console_logs(mock.sentinel.instance_name,
                                            mock.sentinel.dest_host)

        self._pathutils.get_vm_console_log_paths.assert_has_calls(
            [mock.call(mock.sentinel.instance_name),
             mock.call(mock.sentinel.instance_name,
                       remote_server=mock.sentinel.dest_host)])
        self._pathutils.copy.assert_has_calls([
            mock.call(mock.sentinel.log_path,
                      mock.sentinel.remote_log_path),
            mock.call(mock.sentinel.archived_log_path,
                      mock.sentinel.remote_archived_log_path)])

    @mock.patch.object(pathutils.PathUtils, 'get_base_vhd_dir')
    @mock.patch.object(pathutils.PathUtils, 'exists')
    def _test_get_image_path(self, mock_exists, mock_get_base_vhd_dir,
                             found=True):
        fake_image_name = 'fake_image_name'
        if found:
            mock_exists.side_effect = [False, True]
        else:
            mock_exists.return_value = False
        mock_get_base_vhd_dir.return_value = 'fake_base_dir'

        res = self._pathutils.get_image_path(fake_image_name)

        mock_get_base_vhd_dir.assert_called_once_with()
        if found:
            self.assertEqual(
                res, os.path.join('fake_base_dir', 'fake_image_name.vhdx'))
        else:
            self.assertIsNone(res)

    def test_get_image_path(self):
        self._test_get_image_path()

    def test_get_image_path_not_found(self):
        self._test_get_image_path(found=False)

    @mock.patch('os.path.getmtime')
    @mock.patch.object(pathutils, 'time')
    def test_get_age_of_file(self, mock_time, mock_getmtime):
        mock_time.time.return_value = time.time()
        mock_getmtime.return_value = mock_time.time.return_value - 42

        actual_age = self._pathutils.get_age_of_file(mock.sentinel.filename)
        self.assertEqual(42, actual_age)
        mock_time.time.assert_called_once_with()
        mock_getmtime.assert_called_once_with(mock.sentinel.filename)

    @mock.patch('os.path.exists')
    @mock.patch('tempfile.NamedTemporaryFile')
    def test_check_dirs_shared_storage(self, mock_named_tempfile,
                                       mock_exists):
        fake_src_dir = 'fake_src_dir'
        fake_dest_dir = 'fake_dest_dir'

        mock_exists.return_value = True
        mock_tmpfile = mock_named_tempfile.return_value.__enter__.return_value
        mock_tmpfile.name = 'fake_tmp_fname'
        expected_src_tmp_path = os.path.join(fake_src_dir,
                                             mock_tmpfile.name)

        self._pathutils.check_dirs_shared_storage(
            fake_src_dir, fake_dest_dir)

        mock_named_tempfile.assert_called_once_with(dir=fake_dest_dir)
        mock_exists.assert_called_once_with(expected_src_tmp_path)

    @mock.patch.object(pathutils.PathUtils, 'check_dirs_shared_storage')
    @mock.patch.object(pathutils.PathUtils, 'get_instances_dir')
    def test_check_remote_instances_shared(self, mock_get_instances_dir,
                                           mock_check_dirs_shared_storage):
        mock_get_instances_dir.side_effect = [mock.sentinel.local_inst_dir,
                                              mock.sentinel.remote_inst_dir]

        shared_storage = self._pathutils.check_remote_instances_dir_shared(
            mock.sentinel.dest)

        self.assertEqual(mock_check_dirs_shared_storage.return_value,
                         shared_storage)
        mock_get_instances_dir.assert_has_calls(
            [mock.call(), mock.call(mock.sentinel.dest)])
        mock_check_dirs_shared_storage.assert_called_once_with(
            mock.sentinel.local_inst_dir, mock.sentinel.remote_inst_dir)
