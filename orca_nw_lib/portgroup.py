from orca_nw_lib.common import Speed
from orca_nw_lib.device_db import get_device_db_obj
from orca_nw_lib.graph_db_models import PortGroup
from orca_nw_lib.portgroup_gnmi import (
    get_port_group_from_device,
    set_port_group_speed_on_device,
)
from orca_nw_lib.portgroup_db import (
    get_port_group_member_from_db,
    get_port_group_member_names_from_db,
    insert_device_port_groups_in_db,
    get_port_group_from_db,
)
from orca_nw_lib.utils import get_logging
from grpc._channel import _InactiveRpcError


_logger = get_logging().getLogger(__name__)


def _create_port_group_graph_objects(device_ip: str):
    """
    Create port group graph objects based on the given device IP.

    Args:
        device_ip (str): The IP address of the device.

    Returns:
        dict: A dictionary of port group graph objects. The keys are PortGroup objects
            and the values are lists of member interfaces.

    """
    port_groups_json = get_port_group_from_device(device_ip)
    port_group_graph_objs = {}
    for port_group in port_groups_json.get("openconfig-port-group:port-group") or []:
        port_group_state = port_group.get("state", {})
        default_speed = Speed.getSpeedStrFromOCStr(
            port_group_state.get("default-speed")
        )
        member_if_start = port_group_state.get("member-if-start")
        member_if_end = port_group_state.get("member-if-end")
        valid_speeds = [
            Speed.getSpeedStrFromOCStr(s) for s in port_group_state.get("valid-speeds")
        ]
        speed = Speed.getSpeedStrFromOCStr(port_group_state.get("speed"))
        gr_id = port_group_state.get("id")

        mem_infcs = []
        for eth_num in range(
            int(member_if_start.replace("Ethernet", "")),
            int(member_if_end.replace("Ethernet", "")) + 1,
        ):
            mem_infcs.append(f"Ethernet{eth_num}")

        port_group_graph_objs[
            PortGroup(
                port_group_id=gr_id,
                speed=speed,
                valid_speeds=valid_speeds,
                default_speed=default_speed,
            )
        ] = mem_infcs

    return port_group_graph_objs


def get_port_group_members(device_ip: str, group_id):
    """
    Retrieves the members of a port group based on the device IP and group ID.

    Args:
        device_ip (str): The IP address of the device.
        group_id: The ID of the port group.

    Returns:
        list: A list of dictionaries representing the properties of each member interface.
    """
    op_dict = []
    mem_intfcs = get_port_group_member_from_db(device_ip, group_id)
    if mem_intfcs:
        for mem_if in mem_intfcs or []:
            op_dict.append(mem_if.__properties__)
    return op_dict


def get_port_groups(device_ip: str, port_group_id=None):
    if port_group_id:
        db_output = (
            port_group.__properties__
            if (port_group := get_port_group_from_db(device_ip, port_group_id))
            else None
        )
        db_output["mem_intfs"] = get_port_group_member_names_from_db(
            device_ip, db_output.get("port_group_id")
        )
        return db_output
    else:
        db_output = [
            pg.__properties__ for pg in get_port_group_from_db(device_ip) or []
        ]
        if db_output:
            for pg in db_output or []:
                pg["mem_intfs"] = get_port_group_member_names_from_db(
                    device_ip, pg.get("port_group_id")
                )
        return db_output


def discover_port_groups(device_ip: str = None):
    _logger.info("Port-groups Discovery Started.")
    devices = [get_device_db_obj(device_ip)] if device_ip else get_device_db_obj()
    for device in devices:
        _logger.info(f"Discovering port-groups of device {device}.")
        insert_device_port_groups_in_db(
            device, _create_port_group_graph_objects(device.mgt_ip)
        )


def set_port_group_speed(device_ip: str, port_group_id: str, speed: Speed):
    try:
        set_port_group_speed_on_device(device_ip, port_group_id, speed)
    except _InactiveRpcError as err:
        _logger.error(
            f"Port Group {port_group_id} speed change failed on device {device_ip}, Reason: {err.details()}"
        )
        raise
    finally:
        discover_port_groups(device_ip)
