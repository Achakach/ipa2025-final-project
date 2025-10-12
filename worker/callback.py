import json
from router_client import (
    get_interfaces,
    backup_config,
    restore_config,
    configure_interface,
    configure_dns,
)
from database import save_interface_status, save_backup_config


def callback(ch, method, props, body):
    job = json.loads(body.decode())
    # กำหนดค่าเริ่มต้นให้เป็น 'check_interface' ถ้าไม่มี job_type ส่งมา
    job_type = job.get("job_type", "check_interface")

    router_ip = job["ip"]
    router_username = job["user"]
    router_password = job["password"]

    print(f"Received job '{job_type}' for router {router_ip}")

    try:
        if job_type == "check_interface":
            output = get_interfaces(router_ip, router_username, router_password)
            save_interface_status(router_ip, output)
            print(f"Stored interface status for {router_ip}")

        elif job_type == "backup":
            output = backup_config(router_ip, router_username, router_password)
            save_backup_config(router_ip, output)
            print(f"Stored backup config for {router_ip}")

        elif job_type == "restore":
            config_text = job.get("config")
            if config_text:
                restore_config(router_ip, router_username, router_password, config_text)
                print(f"Successfully sent restore job for {router_ip}")

        elif job_type == "configure_interface":
            interface_name = job.get("interface_name")
            config_type = job.get("config_type")
            ip_address = job.get("ip_address")
            subnet_prefix = job.get("subnet_prefix")

            configure_interface(
                router_ip,
                router_username,
                router_password,
                interface_name,
                config_type,
                ip_address,
                subnet_prefix,
            )
            print(
                f"Successfully sent configure job for {interface_name} on {router_ip}"
            )

        elif job_type == "configure_dns":
            dns_servers = job.get("dns_servers", [])
            configure_dns(router_ip, router_username, router_password, dns_servers)
            print(f"Successfully sent DNS config job for {router_ip}")

    except Exception as e:
        print(f" Error: {e}")
