from typing import List, Optional
from .device_db import get_device_db_obj
from .graph_db_models import Device, Vlan
from .interface_db import getInterfaceOfDeviceFromDB
from .vlan_gnmi import get_vlan_details_from_device


def del_vlan_from_db(device_ip, vlan_name: str = None):
    """
    Deletes a VLAN from the database.

    Parameters:
        device_ip (str): The IP address of the device.
        vlan_name (str, optional): The name of the VLAN to be deleted. Defaults to None.

    Returns:
        None
    """
    device: Device = get_device_db_obj(device_ip)
    vlan = device.vlans.get_or_none(name=vlan_name) if device else None
    if vlan:
        vlan.delete()


def get_vlan_obj_from_db(device_ip, vlan_name: str = None):
    """
    Get the VLAN object from the database.

    Parameters:
        device_ip (str): The IP address of the device.
        vlan_name (str, optional): The name of the VLAN. Defaults to None.

    Returns:
        The VLAN object from the database if `vlan_name` is None, otherwise the VLAN object with the specified name.
    """
    device: Device = get_device_db_obj(device_ip)
    return (
        device.vlans.all()
        if not vlan_name
        else device.vlans.get_or_none(name=vlan_name)
    )


def get_vlan_mem_ifcs_from_db(device_ip: str, vlan_name: str) -> Optional[List[str]]:
    """
    Retrieves the member interfaces of a specific VLAN from the device database.

    Args:
        device_ip (str): The IP address of the device.
        vlan_name (str): The name of the VLAN.

    Returns:
        List[str]: A list of member interfaces if the device and VLAN exist in the database, 
        otherwise None.
    """

    device: Device = get_device_db_obj(device_ip)
    return (
        v.memberInterfaces.all()
        if device and device.vlans and (v := device.vlans.get_or_none(name=vlan_name))
        else None
    )


def copy_vlan_obj_prop(target_vlan_obj: Vlan, source_vlan_obj: Vlan):
    """
    Copy the properties of one VLAN object to another.

    Args:
        target_vlan_obj (Vlan): The target VLAN object to copy the properties to.
        source_vlan_obj (Vlan): The source VLAN object to copy the properties from.

    Returns:
        None
    """
    target_vlan_obj.vlanid = source_vlan_obj.vlanid
    target_vlan_obj.name = source_vlan_obj.name
    target_vlan_obj.mtu = source_vlan_obj.mtu
    target_vlan_obj.admin_status = source_vlan_obj.admin_status
    target_vlan_obj.oper_status = source_vlan_obj.oper_status


def insert_vlan_in_db(device: Device, vlans_obj_vs_mem):
    """
    Inserts VLAN information into the database.

    Args:
        device (Device): The device object representing the device.
        vlans_obj_vs_mem (dict): A dictionary containing VLAN objects as keys 
        and a list of members as values.

    Returns:
        None
    """
    for vlan, members in vlans_obj_vs_mem.items():
        if v := get_vlan_obj_from_db(device.mgt_ip, vlan.name):
            # update existing vlan
            copy_vlan_obj_prop(v, vlan)
            v.save()
            device.vlans.connect(v)
        else:
            vlan.save()
            device.vlans.connect(vlan)

        saved_vlan = get_vlan_obj_from_db(device.mgt_ip, vlan.name)
        for mem in members:
            mem_rel = (
                saved_vlan.memberInterfaces.connect(intf)
                if saved_vlan
                and (
                    intf := getInterfaceOfDeviceFromDB(device.mgt_ip, mem.get("ifname"))
                )
                else None
            )
            mem_rel.tagging_mode = mem.get("tagging_mode")
            mem_rel.save()
    ## Handle the case when some or all vlans has been deleted from device but remained in DB
    ## Remove all vlans which are in DB but not on device
    for vlan_in_db in get_vlan_obj_from_db(device.mgt_ip):
        if vlan_in_db not in vlans_obj_vs_mem:
            del_vlan_from_db(device.mgt_ip, vlan_in_db.name)


def get_vlan_db_obj(device_ip: str, vlan_name: str = None):
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
        vlans.append(
            Vlan(
                vlanid=vlan.get("vlanid"),
                name=vlan.get("name"),
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