import unittest
import mock
import os

import pytest

from .device_mocks.ios import send_command, send_command_expect
from pyntc.devices.base_device import RollbackError
from pyntc.devices import IOSDevice
from pyntc.devices import ios_device as ios_module


BOOT_IMAGE = "c3560-advipservicesk9-mz.122-44.SE"
BOOT_OPTIONS_PATH = "pyntc.devices.ios_device.IOSDevice.boot_options"


class TestIOSDevice(unittest.TestCase):
    @mock.patch.object(IOSDevice, "open")
    @mock.patch.object(IOSDevice, "close")
    @mock.patch("netmiko.cisco.cisco_ios.CiscoIosSSH", autospec=True)
    def setUp(self, mock_miko, mock_close, mock_open):
        self.device = IOSDevice("host", "user", "pass")

        mock_miko.send_command_timing.side_effect = send_command
        mock_miko.send_command_expect.side_effect = send_command_expect
        self.device.native = mock_miko

    def tearDown(self):
        # Reset the mock so we don't have transient test effects
        self.device.native.reset_mock()

    def test_config(self):
        command = "interface fastEthernet 0/1"
        result = self.device.config(command)

        self.assertIsNone(result)
        self.device.native.send_command_timing.assert_called_with(command)

    def test_bad_config(self):
        command = "asdf poknw"

        try:
            with self.assertRaisesRegex(ios_module.CommandError, command):
                self.device.config(command)
        finally:
            self.device.native.reset_mock()

    def test_config_list(self):
        commands = ["interface fastEthernet 0/1", "no shutdown"]
        result = self.device.config_list(commands)

        self.assertIsNone(result)

        for cmd in commands:
            self.device.native.send_command_timing.assert_any_call(cmd)

    def test_bad_config_list(self):
        commands = ["interface fastEthernet 0/1", "apons"]
        results = ["ok", "Error: apons"]

        self.device.native.send_command_timing.side_effect = results

        with self.assertRaisesRegex(ios_module.CommandListError, commands[1]):
            self.device.config_list(commands)

    def test_show(self):
        command = "show ip arp"
        result = self.device.show(command)

        self.assertIsInstance(result, str)
        self.assertIn("Protocol", result)
        self.assertIn("Address", result)

        self.device.native.send_command_timing.assert_called_with(command)

    def test_bad_show(self):
        command = "show microsoft"
        self.device.native.send_command_timing.return_value = "Error: Microsoft"
        with self.assertRaises(ios_module.CommandError):
            self.device.show(command)

    def test_show_list(self):
        commands = ["show version", "show clock"]

        result = self.device.show_list(commands)
        self.assertIsInstance(result, list)

        self.assertIn("uptime is", result[0])
        self.assertIn("UTC", result[1])

        calls = list(mock.call(x) for x in commands)
        self.device.native.send_command_timing.assert_has_calls(calls)

    def test_bad_show_list(self):
        commands = ["show badcommand", "show clock"]
        results = ["Error: badcommand", "14:31:57.089 PST Tue Feb 10 2008"]

        self.device.native.send_command_timing.side_effect = results

        with self.assertRaisesRegex(ios_module.CommandListError, "show badcommand"):
            self.device.show_list(commands)

    def test_save(self):
        result = self.device.save()
        self.assertTrue(result)
        self.device.native.send_command_timing.assert_any_call("copy running-config startup-config")

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertTrue(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists_bad_md5(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = True
        mock_ft_instance.compare_md5.return_value = False

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_remote_exists_not(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = True

        result = self.device.file_copy_remote_exists("source_file")

        self.assertFalse(result)

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"

        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("path/to/source_file")

        mock_ft.assert_called_with(self.device.native, "path/to/source_file", "source_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_different_dest(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value

        mock_ft_instance.check_file_exists.side_effect = [False, True]
        self.device.file_copy("source_file", "dest_file")

        mock_ft.assert_called_with(self.device.native, "source_file", "dest_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_fail(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = Exception
        mock_ft_instance.check_file_exists.return_value = False

        with self.assertRaises(ios_module.FileTransferError):
            self.device.file_copy("source_file")

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_socket_closed_good_md5(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = OSError
        mock_ft_instance.check_file_exists.side_effect = [False, True]
        mock_ft_instance.compare_md5.side_effect = [True, True]

        self.device.file_copy("path/to/source_file")

        mock_ft.assert_called_with(self.device.native, "path/to/source_file", "source_file", file_system="flash:")
        mock_ft_instance.enable_scp.assert_any_call()
        mock_ft_instance.establish_scp_conn.assert_any_call()
        mock_ft_instance.transfer_file.assert_any_call()
        mock_ft_instance.compare_md5.assert_has_calls([mock.call(), mock.call()])

    @mock.patch("pyntc.devices.ios_device.FileTransfer", autospec=True)
    def test_file_copy_fail_socket_closed_bad_md5(self, mock_ft):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = "flash: /dev/null"
        mock_ft_instance = mock_ft.return_value
        mock_ft_instance.transfer_file.side_effect = OSError
        mock_ft_instance.check_file_exists.return_value = False
        mock_ft_instance.compare_md5.return_value = False

        with self.assertRaises(ios_module.SocketClosedError):
            self.device.file_copy("source_file")

        mock_ft_instance.compare_md5.assert_called_once()

    def test_reboot(self):
        self.device.reboot(confirm=True)
        self.device.native.send_command_timing.assert_any_call("reload")

    def test_reboot_with_timer(self):
        self.device.reboot(confirm=True, timer=5)
        self.device.native.send_command_timing.assert_any_call("reload in 5")

    def test_reboot_no_confirm(self):
        self.device.reboot()
        assert not self.device.native.send_command_timing.called

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="bootflash:")
    def test_boot_options_show_bootvar(self, mock_boot):
        self.device.native.send_command_timing.side_effect = None
        self.device.native.send_command_timing.return_value = f"BOOT variable = bootflash:{BOOT_IMAGE}"
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command_timing.assert_called_with("show bootvar")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    def test_boot_options_show_boot(self, mock_boot):
        show_boot_out = (
            "Current Boot Variables:\n"
            "BOOT variable = flash:/cat3k_caa-universalk9.16.11.03a.SPA.bin;\n\n"
            "Boot Variables on next reload:\n"
            f"BOOT variable = flash:/{BOOT_IMAGE};\n"
            "Manual Boot = no\n"
            "Enable Break = no\n"
            "Boot Mode = DEVICE\n"
            "iPXE Timeout = 0"
        )
        results = [ios_module.CommandError("show bootvar", "fail"), show_boot_out]
        self.device.native.send_command_timing.side_effect = results
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command_timing.assert_called_with("show boot")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="bootflash:")
    def test_boot_options_show_run(self, mock_boot):
        results = [
            ios_module.CommandError("show bootvar", "fail"),
            ios_module.CommandError("show bootvar", "fail"),
            f"boot system flash bootflash:/{BOOT_IMAGE}",
            "Directory of bootflash:/",
        ]
        self.device.native.send_command_timing.side_effect = results
        boot_options = self.device.boot_options
        self.assertEqual(boot_options, {"sys": BOOT_IMAGE})
        self.device.native.send_command_timing.assert_called_with("show run | inc boot")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    @mock.patch.object(IOSDevice, "config_list", return_value=None)
    def test_set_boot_options(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE)
            mock_cl.assert_called_with(["no boot system", f"boot system flash:/{BOOT_IMAGE}"])

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    @mock.patch.object(IOSDevice, "config_list", side_effect=[ios_module.CommandError("boot system", "fail"), None])
    def test_set_boot_options_with_spaces(self, mock_cl, mock_fs):
        with mock.patch(BOOT_OPTIONS_PATH, new_callable=mock.PropertyMock) as mock_boot:
            mock_boot.return_value = {"sys": BOOT_IMAGE}
            self.device.set_boot_options(BOOT_IMAGE)
            mock_cl.assert_called_with(["no boot system", f"boot system flash {BOOT_IMAGE}"])

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    def test_set_boot_options_no_file(self, mock_fs):
        with self.assertRaises(ios_module.NTCFileNotFoundError):
            self.device.set_boot_options("bad_image.bin")

    @mock.patch.object(IOSDevice, "_get_file_system", return_value="flash:")
    @mock.patch.object(IOSDevice, "boot_options", return_value={"sys": "bad_image.bin"})
    @mock.patch.object(IOSDevice, "config_list", return_value=None)
    def test_set_boot_options_bad_boot(self, mock_cl, mock_bo, mock_fs):
        with self.assertRaises(ios_module.CommandError):
            self.device.set_boot_options(BOOT_IMAGE)
            mock_bo.assert_called_once()

    def test_backup_running_config(self):
        filename = "local_running_config"
        self.device.backup_running_config(filename)

        with open(filename, "r") as f:
            contents = f.read()

        self.assertEqual(contents, self.device.running_config)
        os.remove(filename)

    def test_rollback(self):
        self.device.rollback("good_checkpoint")
        self.device.native.send_command_timing.assert_called_with("configure replace flash:good_checkpoint force")

    def test_bad_rollback(self):
        # TODO: change to what the protocol would return
        self.device.native.send_command_timing.return_value = "Error: rollback unsuccessful"
        with self.assertRaises(RollbackError):
            self.device.rollback("bad_checkpoint")

    def test_checkpoint(self):
        self.device.checkpoint("good_checkpoint")
        self.device.native.send_command_timing.assert_any_call("copy running-config good_checkpoint")

    def test_facts(self):
        expected = {
            "uptime": 413940,
            "vendor": "cisco",
            "uptime_string": "04:18:59:00",
            "interfaces": ["FastEthernet0/0", "FastEthernet0/1"],
            "hostname": "rtr2811",
            "fqdn": "N/A",
            "os_version": "15.1(3)T4",
            "serial_number": "",
            "model": "2811",
            "vlans": [],
            "cisco_ios_ssh": {"config_register": "0x2102"},
        }
        facts = self.device.facts
        self.assertEqual(facts, expected)

        self.device.native.send_command_timing.reset_mock()
        facts = self.device.facts
        self.assertEqual(facts, expected)

        self.device.native.send_command_timing.assert_not_called()

    def test_running_config(self):
        expected = self.device.show("show running-config")
        self.assertEqual(self.device.running_config, expected)

    def test_starting_config(self):
        expected = self.device.show("show startup-config")
        self.assertEqual(self.device.startup_config, expected)

    def test_enable_from_disable(self):
        self.device.native.check_enable_mode.return_value = False
        self.device.native.check_config_mode.return_value = False
        self.device.enable()
        self.device.native.check_enable_mode.assert_called()
        self.device.native.enable.assert_called()
        self.device.native.check_config_mode.assert_called()
        self.device.native.exit_config_mode.assert_not_called()

    def test_enable_from_enable(self):
        self.device.native.check_enable_mode.return_value = True
        self.device.native.check_config_mode.return_value = False
        self.device.enable()
        self.device.native.check_enable_mode.assert_called()
        self.device.native.enable.assert_not_called()
        self.device.native.check_config_mode.assert_called()
        self.device.native.exit_config_mode.assert_not_called()

    def test_enable_from_config(self):
        self.device.native.check_enable_mode.return_value = True
        self.device.native.check_config_mode.return_value = True
        self.device.enable()
        self.device.native.check_enable_mode.assert_called()
        self.device.native.enable.assert_not_called()
        self.device.native.check_config_mode.assert_called()
        self.device.native.exit_config_mode.assert_called()

    @mock.patch.object(IOSDevice, "_image_booted", side_effect=[False, True])
    @mock.patch.object(IOSDevice, "set_boot_options")
    @mock.patch.object(IOSDevice, "reboot")
    @mock.patch.object(IOSDevice, "_wait_for_device_reboot")
    def test_install_os(self, mock_wait, mock_reboot, mock_set_boot, mock_image_booted):
        state = self.device.install_os(BOOT_IMAGE)
        mock_set_boot.assert_called()
        mock_reboot.assert_called()
        mock_wait.assert_called()
        self.assertEqual(state, True)

    @mock.patch.object(IOSDevice, "_image_booted", side_effect=[True])
    @mock.patch.object(IOSDevice, "set_boot_options")
    @mock.patch.object(IOSDevice, "reboot")
    @mock.patch.object(IOSDevice, "_wait_for_device_reboot")
    def test_install_os_already_installed(self, mock_wait, mock_reboot, mock_set_boot, mock_image_booted):
        state = self.device.install_os(BOOT_IMAGE)
        mock_image_booted.assert_called_once()
        mock_set_boot.assert_not_called()
        mock_reboot.assert_not_called()
        mock_wait.assert_not_called()
        self.assertEqual(state, False)

    @mock.patch.object(IOSDevice, "_image_booted", side_effect=[False, False])
    @mock.patch.object(IOSDevice, "set_boot_options")
    @mock.patch.object(IOSDevice, "reboot")
    @mock.patch.object(IOSDevice, "_wait_for_device_reboot")
    def test_install_os_error(self, mock_wait, mock_reboot, mock_set_boot, mock_image_booted):
        self.assertRaises(ios_module.OSInstallError, self.device.install_os, BOOT_IMAGE)


if __name__ == "__main__":
    unittest.main()


@mock.patch.object(IOSDevice, "is_active")
@mock.patch.object(IOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
def test_confirm_is_active(mock_redundancy_state, mock_is_active, ios_device):
    mock_is_active.return_value = True
    actual = ios_device.confirm_is_active()
    assert actual is True
    mock_redundancy_state.assert_not_called()


@mock.patch.object(IOSDevice, "is_active")
@mock.patch.object(IOSDevice, "peer_redundancy_state", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "close")
@mock.patch.object(IOSDevice, "open")
@mock.patch("pyntc.devices.ios_device.ConnectHandler")
def test_confirm_is_active_not_active(
    mock_connect_handler, mock_open, mock_close, mock_redundancy_state, mock_peer_redundancy_state, mock_is_active
):
    mock_is_active.return_value = False
    mock_redundancy_state.return_value = "standby hot"
    device = IOSDevice("host", "user", "password")
    with pytest.raises(ios_module.DeviceNotActiveError):
        device.confirm_is_active()

    mock_redundancy_state.assert_called_once()
    mock_peer_redundancy_state.assert_called_once()
    mock_close.assert_called_once()


@pytest.mark.parametrize("expected", ((True,), (False,)))
def test_connected_getter(expected, ios_device):
    ios_device._connected = expected
    assert ios_device.connected is expected


@pytest.mark.parametrize("expected", ((True,), (False,)))
def test_connected_setter(expected, ios_device):
    ios_device._connected = not expected
    assert ios_device._connected is not expected
    ios_device.connected = expected
    assert ios_device._connected is expected


@mock.patch.object(IOSDevice, "redundancy_state", new_callable=mock.PropertyMock)
@pytest.mark.parametrize(
    "redundancy_state,expected",
    (
        ("active", True),
        ("standby hot", False),
        (None, True),
    ),
    ids=("active", "standby_hot", "unsupported"),
)
def test_is_active(mock_redundancy_state, ios_device, redundancy_state, expected):
    mock_redundancy_state.return_value = redundancy_state
    actual = ios_device.is_active()
    assert actual is expected


@mock.patch("pyntc.devices.ios_device.ConnectHandler")
@mock.patch.object(IOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_prompt_found(mock_connected, mock_connect_handler, ios_device):
    mock_connected.return_value = True
    ios_device.open()
    assert ios_device._connected is True
    ios_device.native.find_prompt.assert_called()
    mock_connected.assert_has_calls((mock.call(), mock.call()))
    mock_connect_handler.assert_not_called()


@mock.patch("pyntc.devices.ios_device.ConnectHandler")
@mock.patch.object(IOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_prompt_not_found(mock_connected, mock_connect_handler, ios_device):
    mock_connected.side_effect = [True, False]
    ios_device.native.find_prompt.side_effect = [Exception]
    ios_device.open()
    assert ios_device._connected is True
    mock_connected.assert_has_calls((mock.call(), mock.call()))
    mock_connect_handler.assert_called()


@mock.patch("pyntc.devices.ios_device.ConnectHandler")
@mock.patch.object(IOSDevice, "connected", new_callable=mock.PropertyMock)
def test_open_not_connected(mock_connected, mock_connect_handler, ios_device):
    mock_connected.return_value = False
    ios_device._connected = False
    ios_device.open()
    assert ios_device._connected is True
    ios_device.native.find_prompt.assert_not_called()
    mock_connected.assert_has_calls((mock.call(), mock.call()))
    mock_connect_handler.assert_called()


@mock.patch("pyntc.devices.ios_device.ConnectHandler")
@mock.patch.object(IOSDevice, "connected", new_callable=mock.PropertyMock)
@mock.patch.object(IOSDevice, "confirm_is_active")
def test_open_standby(mock_confirm, mock_connected, mock_connect_handler, ios_device):
    mock_connected.side_effect = [False, False, True]
    mock_confirm.side_effect = [ios_module.DeviceNotActiveError("host1", "standby", "active")]
    with pytest.raises(ios_module.DeviceNotActiveError):
        ios_device.open()

    ios_device.native.find_prompt.assert_not_called()
    mock_connected.assert_has_calls((mock.call(),) * 2)


@pytest.mark.parametrize(
    "filename,expected",
    (
        ("show_redundancy", "standby hot"),
        ("show_redundancy_no_peer", "disabled"),
    ),
    ids=("standby_hot", "disabled"),
)
def test_peer_redundancy_state(filename, expected, ios_show):
    device = ios_show([f"{filename}.txt"])
    actual = device.peer_redundancy_state
    assert actual == expected


def test_peer_redundancy_state_unsupported(ios_show):
    device = ios_show([ios_module.CommandError("show redundancy", "unsupported")])
    actual = device.peer_redundancy_state
    assert actual is None


def test_re_show_redundancy(ios_show, ios_redundancy_info, ios_redundancy_self, ios_redundancy_other):
    device = ios_show(["show_redundancy.txt"])
    show_redundancy = device.show("show redundancy")
    re_show_redundancy = ios_module.RE_SHOW_REDUNDANCY.match(show_redundancy)
    assert re_show_redundancy.groupdict() == {
        "info": ios_redundancy_info,
        "self": ios_redundancy_self,
        "other": ios_redundancy_other,
    }


def test_re_show_redundancy_no_peer(ios_show, ios_redundancy_info, ios_redundancy_self):
    device = ios_show(["show_redundancy_no_peer.txt"])
    show_redundancy = device.show("show redundancy")
    re_show_redundancy = ios_module.RE_SHOW_REDUNDANCY.match(show_redundancy)
    assert re_show_redundancy.groupdict() == {
        "info": ios_redundancy_info,
        "self": ios_redundancy_self,
        "other": None,
    }


def test_re_redundancy_operation_mode(ios_redundancy_info):
    re_operational_mode = ios_module.RE_REDUNDANCY_OPERATION_MODE.search(ios_redundancy_info)
    assert re_operational_mode.group(1) == "Stateful Switchover"


@pytest.mark.parametrize(
    "output,expected",
    (
        ("a\n  Current Software state = ACTIVE \n  b", "ACTIVE"),
        ("a\n  Current Software state = STANDBY HOT \n  b", "STANDBY HOT"),
    ),
    ids=("active", "standby_hot"),
)
def test_re_redundancy_state(output, expected):
    re_redundancy_state = ios_module.RE_REDUNDANCY_STATE.search(output)
    actual = re_redundancy_state.group(1)
    assert actual == expected


def test_redundancy_mode(ios_show):
    device = ios_show(["show_redundancy.txt"])
    actual = device.redundancy_mode
    assert actual == "stateful switchover"


def test_redundancy_mode_unsupported_command(ios_show):
    device = ios_show([ios_module.CommandError("show redundancy", "unsupported")])
    actual = device.redundancy_mode
    assert actual == "n/a"


@pytest.mark.parametrize(
    "filename,expected",
    (
        ("show_redundancy", "active"),
        ("show_redundancy_standby", "standby hot"),
    ),
    ids=("active", "standby_hot"),
)
def test_redundancy_state(filename, expected, ios_show):
    device = ios_show([f"{filename}.txt"])
    actual = device.redundancy_state
    assert actual == expected


def test_redundancy_state_unsupported(ios_show):
    device = ios_show([ios_module.CommandError("show redundancy", "unsupported")])
    actual = device.redundancy_state
    assert actual is None


def test_get_file_system(ios_show):
    filename = "dir"
    expected = "flash:"
    device = ios_show([f"{filename}.txt"])
    actual = device._get_file_system()
    assert actual == expected


def test_get_file_system_first_error_then_pass(ios_show):
    filename = "dir"
    expected = "flash:"
    device = ios_show(["", f"{filename}.txt"])
    actual = device._get_file_system()
    assert actual == expected

    device.show.assert_has_calls([mock.call("dir")] * 2)


@mock.patch.object(IOSDevice, "facts", new_callable=mock.PropertyMock)
def test_get_file_system_raise_error(mock_facts, ios_show):
    # Set the command to run 5 times
    device = ios_show([""] * 5)

    # Set a return value for the Facts mock
    mock_facts.return_value = {"hostname": "pyntc-rtr"}

    # Test with the raises
    with pytest.raises(ios_module.FileSystemNotFoundError):
        device._get_file_system()

    # Assert of the calls
    device.show.assert_has_calls([mock.call("dir")] * 5)


def test_send_command_error(ios_send_command_timing):
    command = "send_command_error"
    device = ios_send_command_timing([f"{command}.txt"])
    with pytest.raises(ios_module.CommandError):
        device._send_command(command)
    device.native.send_command_timing.assert_called()


def test_send_command_expect(ios_send_command):
    command = "send_command_expect"
    device = ios_send_command([f"{command}.txt"])
    device._send_command(command, expect_string="Continue?")
    device.native.send_command.assert_called_with("send_command_expect", expect_string="Continue?")


def test_send_command_timing(ios_send_command_timing):
    command = "send_command_timing"
    device = ios_send_command_timing([f"{command}.txt"])
    device._send_command(command)
    device.native.send_command_timing.assert_called()
    device.native.send_command_timing.assert_called_with(command)
