from orca_nw_lib.utils import get_logging

from orca_nw_lib.common import STPPortEdgePort
from orca_nw_lib.device_db import get_device_db_obj

from orca_nw_lib.gnmi_sub import check_gnmi_subscription_and_apply_config
from orca_nw_lib.graph_db_models import STP_PORT
from orca_nw_lib.stp_port_db import (get_stp_port_members_from_db, insert_device_stp_port_in_db)
from orca_nw_lib.stp_port_gnmi import (add_stp_port_members_on_device,
                                       get_stp_port_members_from_device,
                                       delete_stp_port_member_from_device)

_logger = get_logging().getLogger(__name__)


def _create_stp_port_graph_object(device_ip: str):
    """
    Creates the STP port graph object.

    Parameters:
        device_ip (str): The IP address of the device.

    Returns:
        dict: The STP port graph object.
    """
    try:
        stp_port_config = get_stp_port_members_from_device(device_ip)
    except Exception as e:
        _logger.error(f"Error getting stp port members from device {device_ip}: {e}")
        return {}
    stp_port_obj_list = {}
    members = []
    _logger.debug(f"Retrieved stp global info from device {device_ip} {stp_port_config}")
    stp_ports = stp_port_config.get("openconfig-spanning-tree:interface", [])
    for port in stp_ports:
        if_name = port.get("name")
        config = port.get("config", {})
        edge_port = config.get("edge-port")
        link_type = config.get("link-type")
        guard = config.get("guard")
        stp_port_obj_list[
            STP_PORT(
                if_name=if_name,
                edge_port=STPPortEdgePort.getSTPPortEdgePortStrFromOCStr(edge_port) if edge_port else None,
                link_type=link_type if link_type else None,
                guard=guard if guard else None,
                bpdu_filter=config.get("bpdu-filter", None),
                bpdu_guard=config.get("bpdu-guard", None),
                bpdu_guard_port_shutdown=config.get("openconfig-spanning-tree-ext:bpdu-guard-port-shutdown", None),
                portfast=config.get("openconfig-spanning-tree-ext:portfast", None),
                uplink_fast=config.get("openconfig-spanning-tree-ext:uplink-fast", None),
                cost=config.get("openconfig-spanning-tree-ext:cost", None),
                port_priority=config.get("openconfig-spanning-tree-ext:port-priority", None),
                stp_enabled=config.get("openconfig-spanning-tree-ext:spanning-tree-enable", None)
            )
        ] = members
    return stp_port_obj_list


def discover_stp_port(device_ip: str = None):
    """
    Discovers the STP port configuration on a device.

    Parameters:
        device_ip (str): The IP address of the device.

    Returns:
        dict: The STP port configuration.
    """
    _logger.info("Discovering STP Port.")
    devices = [get_device_db_obj(device_ip)] if device_ip else get_device_db_obj()
    for device in devices:
        _logger.info(f"Discovering STP on device {device}.")
        try:
            insert_device_stp_port_in_db(device, _create_stp_port_graph_object(device.mgt_ip))
        except Exception as e:
            _logger.error(f"Failed to discover STP, Reason: {e}")
            raise


@check_gnmi_subscription_and_apply_config
def add_stp_port_members(
        device_ip: str, if_name: str, edge_port: str = None, link_type: str = None, guard: str = None,
        bpdu_guard: bool = None, bpdu_filter: bool = None, portfast: bool = None, uplink_fast: bool = None,
        bpdu_guard_port_shutdown: bool = None, cost: int = None, port_priority: int = None,
        stp_enabled: bool = None
):
    """
    Adds the STP port channel members on a device.

    Parameters:
        device_ip (str): The IP address of the device.
        if_name (str, optional): The interface name. Defaults to None.
        edge_port (str, optional): The edge port. Defaults to None.
        link_type (str, optional): The link type. Defaults to None.
        guard (str, optional): The guard. Defaults to None.
        bpdu_guard (str, optional): The BPDU guard. Defaults to None.
        bpdu_filter (str, optional): The BPDU filter. Defaults to None.
        portfast (str, optional): The portfast. Defaults to None.
        uplink_fast (str, optional): The uplink fast. Defaults to None.
        bpdu_guard_port_shutdown (str, optional): The BPDU guard port shutdown. Defaults to None.
        cost (str, optional): The cost. Defaults to None.
        port_priority (str, optional): The port priority. Defaults to None.
        stp_enabled (str, optional): The STP enabled. Defaults to None.

    Raises:
        Exception: If there is an error while adding STP on the device.
    """
    try:
        add_stp_port_members_on_device(
            device_ip=device_ip,
            if_name=if_name,
            edge_port=edge_port,
            link_type=link_type,
            guard=guard,
            bpdu_guard=bpdu_guard,
            bpdu_filter=bpdu_filter,
            portfast=portfast,
            uplink_fast=uplink_fast,
            bpdu_guard_port_shutdown=bpdu_guard_port_shutdown,
            cost=cost,
            port_priority=port_priority,
            stp_enabled=stp_enabled
        )
    except Exception as e:
        _logger.error(f"Failed to add STP Port Channel Members on device {device_ip}, Reason: {e}")
        raise


def get_stp_port_members(device_ip: str, if_name: str = None):
    """
    Retrieves the STP port members from the database.

    Args:
        device_ip (str): The IP address of the device.
        if_name (str, optional): The name of the interface. Defaults to None.

    Returns:
        list or dict: A list of dictionaries representing the STP port members if `if_name` is None,
                     otherwise a dictionary representing the STP port member.

    Raises:
        None.
    """
    stp_port = get_stp_port_members_from_db(device_ip, if_name)
    if stp_port:
        if isinstance(stp_port, list):
            return [i.__properties__ for i in stp_port]
        else:
            return stp_port.__properties__


@check_gnmi_subscription_and_apply_config
def delete_stp_port_member(device_ip: str, if_name: str):
    """
    Deletes the STP port channel member from the database and rediscover the STP port.

    Args:
        device_ip (str): The IP address of the device.
        if_name (str): The name of the interface.

    Raises:
        Exception: If there is an error while deleting the STP port channel member.

    """
    try:
        delete_stp_port_member_from_device(device_ip, if_name)
    except Exception as e:
        _logger.error(f"Failed to delete STP Port Channel Member on device {device_ip}, Reason: {e}")
        raise
