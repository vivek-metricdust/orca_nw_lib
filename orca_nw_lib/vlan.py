from orca_nw_lib.graph_db_models import Vlan
from orca_nw_lib.vlan_gnmi import get_vlan_details_from_device

from .common import IFMode, VlanAutoState

from .device_db import get_device_db_obj
from .vlan_db import (
    get_vlan_obj_from_db,
    get_vlan_mem_ifcs_from_db,
    insert_vlan_in_db,
)
from .vlan_gnmi import (
    add_vlan_mem_interface_on_device,
    config_vlan_on_device,
    del_vlan_from_device,
    del_vlan_mem_interface_on_device,
    get_vlan_ip_details_from_device,
)
from .utils import get_logging
from .graph_db_models import Vlan

_logger = get_logging().getLogger(__name__)


def _create_vlan_db_obj(device_ip: str, vlan_name: str = None):
    """
    Retrieves VLAN information from a device.

    Args:
        device_ip (str): The IP address of the device.
        vlan_name (str, optional): The name of the VLAN to retrieve information for.
                                   Defaults to None.

    Returns:
        dict: A dictionary mapping Vlan objects to a list of VLAN member information.
              Each Vlan object contains information such as VLAN ID, name, MTU,
              administrative status, operational status, and autostate.
              {<vlan_db_obj>: {'ifname': 'Ethernet64', 'name': 'Vlan1', 'tagging_mode': 'tagged'}}
    """

    vlan_details = get_vlan_details_from_device(device_ip, vlan_name)
    vlans = []
    for vlan in vlan_details.get("sonic-vlan:VLAN_LIST") or []:
        v_name = vlan.get("name")
        ip_details = get_vlan_ip_details_from_device(device_ip, v_name).get("openconfig-if-ip:ipv4", {})
        ipv4_addresses = (
            ip_details.get("addresses", {})
            .get("address", [])
        )
        sag_ipv4_addresses = (
            ip_details.get("openconfig-interfaces-ext:sag-ipv4", {}).get("config", {}).get("static-anycast-gateway", [])
        )
        
        ipv4_addr = None
        for ipv4 in ipv4_addresses:
            if (ip:=ipv4.get("config", {}).get("ip", "")) and (pfx:=ipv4.get("config", {}).get("prefix-length", "")):
                ipv4_addr = f"{ip}/{pfx}"
                break

        vlans.append(
            Vlan(
                vlanid=vlan.get("vlanid"),
                name=v_name,
                ip_address=ipv4_addr,
                sag_ip_address=sag_ipv4_addresses[0] if sag_ipv4_addresses else None,
                autostate = vlan.get("autostate",str(VlanAutoState.disable))
            )
        )

    for vlan in vlan_details.get("sonic-vlan:VLAN_TABLE_LIST") or []:
        for v in vlans:
            if v.name == vlan.get("name"):
                v.mtu = vlan.get("mtu")
                v.admin_status = vlan.get("admin_status")
                v.oper_status = vlan.get("oper_status")
                v.autostate = vlan.get("autostate")

    vlans_obj_vs_mem = {}
    for v in vlans:
        members = []
        for item in vlan_details.get("sonic-vlan:VLAN_MEMBER_LIST") or []:
            if v.name == item.get("name"):
                members.append(item)
        vlans_obj_vs_mem[v] = members

    return vlans_obj_vs_mem


def _getJson(device_ip: str, v: Vlan):
    temp = v.__properties__
    temp["members"] = [
        mem.name for mem in get_vlan_mem_ifcs_from_db(device_ip, temp.get("name")) or []
    ]
    return temp


def get_vlan(device_ip, vlan_name: str = None):
    """
    Get VLAN information for a given device.

    Parameters:
        device_ip (str): The IP address of the device.
        vlan_name (str, optional): The name of the VLAN. Defaults to None.

    Returns:
        list: A list of JSON objects representing the VLAN information.
    """
    vlans = get_vlan_obj_from_db(device_ip, vlan_name)
    if vlans is None:
        return None

    if isinstance(vlans, list):
        return [_getJson(device_ip, v) for v in vlans]

    return _getJson(device_ip, vlans)


def del_vlan(device_ip, vlan_name: str):
    """
    Deletes a VLAN from a device.

    Args:
        device_ip (str): The IP address of the device.
        vlan_name (str): The name of the VLAN to be deleted.

    Returns:
        None
    """

    try:
        del_vlan_from_device(device_ip, vlan_name)
    except Exception as e:
        _logger.error(f"VLAN deletion failed on device {device_ip}, Reason: {e}")
        raise
    finally:
        discover_vlan(device_ip)


def config_vlan(device_ip: str, vlan_name: str, vlan_id: int, **kwargs):
    try:
        config_vlan_on_device(device_ip, vlan_name, vlan_id, **kwargs)
    except Exception as e:
        _logger.error(f"VLAN configuration failed on device {device_ip}, Reason: {e}")
        raise
    finally:
        discover_vlan(device_ip)


def add_vlan_mem(device_ip: str, vlan_id: int, mem_ifs: dict[str:IFMode]):

    try:
        add_vlan_mem_interface_on_device(device_ip, vlan_id, mem_ifs)
    except Exception as e:
        _logger.error(f"VLAN member addition failed on device {device_ip}, Reason: {e}")
        raise
    finally:
        discover_vlan(device_ip)


def get_vlan_members(device_ip, vlan_name: str):
    """
    Retrieves the members of a VLAN on a specific device.

    Args:
        device_ip (str): The IP address of the device.
        vlan_name (str): The name of the VLAN.

    Returns:
        dict: A dictionary mapping member interface names to their corresponding tagging mode.
    """
    members = get_vlan_mem_ifcs_from_db(device_ip, vlan_name)
    mem_intf_vs_tagging_mode = {}
    for mem in members or []:
        mem_rel = get_vlan_obj_from_db(
            device_ip, vlan_name
        ).memberInterfaces.relationship(mem)
        mem_intf_vs_tagging_mode[mem.name] = mem_rel.tagging_mode
    return mem_intf_vs_tagging_mode


def del_vlan_mem(device_ip: str, vlan_id: int, if_name: str = None):
    """
    Deletes a VLAN member from a device.

    Args:
        device_ip (str): The IP address of the device.
        vlan_name (str): The name of the VLAN.
        if_name (str, optional): The name of the interface. Defaults to None.

    Returns:
        None
    """
    try:
        del_vlan_mem_interface_on_device(device_ip, vlan_id, if_name)
    except Exception as e:
        _logger.error(f"VLAN member deletion failed on device {device_ip}, Reason: {e}")
        raise
    finally:
        discover_vlan(device_ip)


def discover_vlan(device_ip: str = None):
    """
    Discovers VLANs on a network device.

    Args:
        device_ip (str, optional): The IP address of the device. Defaults to None.
        vlan_name (str, optional): The name of the VLAN. Defaults to None.

    Returns:
        None
    """

    _logger.info("Discovering VLAN.")
    devices = [get_device_db_obj(device_ip)] if device_ip else get_device_db_obj()
    for device in devices:
        try:
            _logger.info(f"Discovering VLAN on device {device}.")
            insert_vlan_in_db(device, _create_vlan_db_obj(device.mgt_ip))
        except Exception as e:
            _logger.error(f"VLAN Discovery Failed on device {device_ip}, Reason: {e}")
            raise
