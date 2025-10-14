import ansible_runner
import os
import json
import ipaddress


def get_interfaces(ip, username, password):
    private_data_dir = os.path.dirname(__file__)

    inventory = {"all": {"hosts": {ip: None}}}

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbooks/playbook.yml",
        inventory=inventory,
        extravars={"router_user": username, "router_pass": password},
        # quiet=True  <--- แก้ไขบรรทัดนี้
        quiet=False,  # <--- เปลี่ยนเป็น False เพื่อดู output ทั้งหมด
    )

    # (โค้ดส่วนที่เหลือเหมือนเดิม)
    # ...
    for event in result.events:
        if (
            event["event"] == "runner_on_ok"
            and "ansible_facts" in event["event_data"]["res"]
        ):
            if "structured_output" in event["event_data"]["res"]["ansible_facts"]:
                output = event["event_data"]["res"]["ansible_facts"][
                    "structured_output"
                ]
                print("--- FINAL OUTPUT ---")
                print(json.dumps(output, indent=2))
                return output

    print(f"Playbook finished with status: {result.status}")
    print(f"RC: {result.rc}")
    raise Exception(f"Failed to get interface data from {ip}.")


def backup_config(ip, username, password):
    """รัน Ansible Playbook เพื่อ backup config"""
    private_data_dir = os.path.dirname(__file__)

    inventory = {"all": {"hosts": {ip: None}}}

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbooks/backup_playbook.yml",
        inventory=inventory,
        extravars={"router_user": username, "router_pass": password},
        quiet=True,
    )

    # ดึงข้อมูล "fact" ที่เราตั้งไว้ใน playbook กลับมา
    for event in result.events:
        if (
            event["event"] == "runner_on_ok"
            and "ansible_facts" in event["event_data"]["res"]
        ):
            if "backup_config" in event["event_data"]["res"]["ansible_facts"]:
                output = event["event_data"]["res"]["ansible_facts"]["backup_config"]

                # vvv เพิ่ม 3 บรรทัดนี้เพื่อดีบัก vvv
                print("--- RAW BACKUP OUTPUT ---")
                print(output)
                print("-------------------------")

                return output

    raise Exception(f"Failed to backup config from {ip}. Status: {result.status}")


# vvv เพิ่มฟังก์ชันนี้ vvv
def restore_config(ip, username, password, config_content):
    """รัน Ansible Playbook เพื่อ restore config"""
    private_data_dir = os.path.dirname(__file__)

    inventory = {"all": {"hosts": {ip: None}}}

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbooks/restore_playbook.yml",
        inventory=inventory,
        extravars={
            "router_user": username,
            "router_pass": password,
            "config_content": config_content,  # <--- ส่งเนื้อหา config เข้าไป
        },
        quiet=False,  # เปิด verbose เพื่อให้เห็นผลลัพธ์
    )

    if result.status == "failed":
        raise Exception(f"Failed to restore config for {ip}. See logs for details.")

    return result.status


# ^^^ จบฟังก์ชัน ^^^


def configure_interface(
    ip,
    username,
    password,
    interface_name,
    config_type,
    ip_address=None,
    subnet_prefix=None,
):
    """รัน Ansible Playbook เพื่อ config interface"""
    private_data_dir = os.path.dirname(__file__)

    inventory = {"all": {"hosts": {ip: None}}}

    extravars = {
        "router_user": username,
        "router_pass": password,
        "interface_name": interface_name,
        "config_type": config_type,
    }

    if config_type == "manual":
        extravars["ip_address"] = ip_address
        extravars["subnet_prefix"] = subnet_prefix

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbooks/config_interface_playbook.yml",
        inventory=inventory,
        extravars=extravars,
        quiet=False,
    )

    if result.status == "failed":
        raise Exception(
            f"Failed to configure interface {interface_name} for {ip}. See logs for details."
        )

    return result.status


def configure_dns(ip, username, password, dns_servers):
    """รัน Ansible Playbook เพื่อ config DNS servers"""
    private_data_dir = os.path.dirname(__file__)
    inventory = {"all": {"hosts": {ip: None}}}

    # กรองเอาเฉพาะ IP ที่ไม่ว่างเปล่าออกไป
    valid_dns_servers = [server for server in dns_servers if server]

    if not valid_dns_servers:
        print("No valid DNS servers provided. Skipping.")
        return "skipped"

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbooks/config_dns_playbook.yml",
        inventory=inventory,
        extravars={
            "router_user": username,
            "router_pass": password,
            "dns_servers": valid_dns_servers,
        },
        quiet=False,
    )

    if result.status == "failed":
        raise Exception(f"Failed to configure DNS for {ip}. See logs for details.")

    return result.status


def configure_dhcp(
    ip,
    username,
    password,
    pool_name,
    network_address,
    subnet_prefix,
    default_gateway,
    exclude_start_ip,
    exclude_end_ip,
    dns_servers,
):
    """รัน Ansible Playbook เพื่อ config DHCP server"""
    private_data_dir = os.path.dirname(__file__)
    inventory = {"all": {"hosts": {ip: None}}}

    # --- ส่วนที่เปลี่ยนแปลง ---
    # สร้าง object network จาก IP และ prefix ที่ได้รับมา
    network_obj = ipaddress.IPv4Network(
        f"{network_address}/{subnet_prefix}", strict=False
    )
    # ดึงค่า subnet mask ออกมาเป็น string (เช่น '255.255.255.0')
    subnet_mask = str(network_obj.netmask)
    # -----------------------

    valid_dns_servers = [server for server in dns_servers if server]

    extravars = {
        "router_user": username,
        "router_pass": password,
        "pool_name": pool_name,
        "network_address": network_address,
        "subnet_mask": subnet_mask,  # <--- ส่ง subnet_mask ที่คำนวณแล้วไปแทน
        "default_gateway": default_gateway,
        "exclude_start_ip": exclude_start_ip,
        "exclude_end_ip": exclude_end_ip,
        "dhcp_dns_servers": valid_dns_servers,
    }

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbooks/config_dhcp_playbook.yml",
        inventory=inventory,
        extravars=extravars,
        quiet=False,
    )

    if result.status == "failed":
        raise Exception(f"Failed to configure DHCP for {ip}. See logs for details.")

    return result.status


def delete_dhcp_pool(ip, username, password, pool_name):
    """รัน Ansible Playbook เพื่อลบ DHCP pool"""
    private_data_dir = os.path.dirname(__file__)
    inventory = {"all": {"hosts": {ip: None}}}

    extravars = {
        "router_user": username,
        "router_pass": password,
        "pool_name": pool_name,
    }

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbooks/delete_dhcp_playbook.yml",
        inventory=inventory,
        extravars=extravars,
        quiet=False,
    )

    if result.status == "failed":
        raise Exception(f"Failed to delete DHCP pool {pool_name} for {ip}.")

    return result.status


def delete_dns(ip, username, password, dns_server):
    """รัน Ansible Playbook เพื่อลบ DNS server ที่ระบุ"""
    private_data_dir = os.path.dirname(__file__)
    inventory = {"all": {"hosts": {ip: None}}}

    extravars = {
        "router_user": username,
        "router_pass": password,
        "dns_server": dns_server,
    }

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbooks/delete_dns_playbook.yml",
        inventory=inventory,
        extravars=extravars,
        quiet=False,
    )

    if result.status == "failed":
        raise Exception(f"Failed to delete DNS server {dns_server} for {ip}.")

    return result.status


if __name__ == "__main__":
    pass
