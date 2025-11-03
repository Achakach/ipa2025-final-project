import json
from router_client import (
    get_interfaces,
    backup_config,
    restore_config,
    configure_interface,
    configure_dns,
    configure_dhcp,
    delete_dhcp_pool,
    delete_dns,
    save_config,
    configure_acl,
    delete_acl,
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

    # --- 1. เพิ่ม Flag สำหรับตรวจสอบว่าต้อง Refresh ข้อมูลหรือไม่ ---
    needs_refresh = False

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
                needs_refresh = True  # <--- ตั้งค่า Flag

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
            needs_refresh = True  # <--- ตั้งค่า Flag

        elif job_type == "configure_dns":
            dns_servers = job.get("dns_servers", [])
            configure_dns(router_ip, router_username, router_password, dns_servers)
            print(f"Successfully sent DNS config job for {router_ip}")
            needs_refresh = True  # <--- ตั้งค่า Flag

        elif job_type == "delete_dns":
            dns_server = job.get("dns_server")
            if dns_server:
                delete_dns(router_ip, router_username, router_password, dns_server)
                print(
                    f"Successfully sent delete job for DNS server {dns_server} on {router_ip}"
                )
                needs_refresh = True  # <--- ตั้งค่า Flag

        elif job_type == "configure_dhcp":
            configure_dhcp(
                router_ip,
                router_username,
                router_password,
                job.get("pool_name"),
                job.get("network_address"),
                job.get("subnet_prefix"),
                job.get("default_gateway"),
                job.get("exclude_start_ip"),
                job.get("exclude_end_ip"),
                job.get("dns_servers", []),
            )
            print(f"Successfully sent DHCP config job for {router_ip}")
            needs_refresh = True  # <--- ตั้งค่า Flag

        elif job_type == "delete_dhcp_pool":
            pool_name = job.get("pool_name")
            delete_dhcp_pool(router_ip, router_username, router_password, pool_name)
            print(
                f"Successfully sent delete job for DHCP pool {pool_name} on {router_ip}"
            )
            needs_refresh = True  # <--- ตั้งค่า Flag
            
        elif job_type == "save_config":
            save_config(router_ip, router_username, router_password)
            print(f"Successfully sent save configuration job for {router_ip}")
            # การ Save ไม่เปลี่ยน running-config แต่ถ้าอยากให้ Refresh ด้วยก็เปิดบรรทัดล่าง
            # needs_refresh = True
            
        elif job_type == "configure_acl":
            configure_acl(
                router_ip,
                router_username,
                router_password,
                job.get("acl_number"),
                job.get("rules", []),
                job.get("interface_name"),
                job.get("direction"),
            )
            print(f"Successfully sent ACL config job for {router_ip}")
            needs_refresh = True  # <--- ตั้งค่า Flag
            
        elif job_type == "delete_acl":
            acl_number = job.get("acl_number")
            if acl_number:
                delete_acl(router_ip, router_username, router_password, acl_number)
                print(
                    f"Successfully sent delete job for ACL {acl_number} on {router_ip}"
                )
                needs_refresh = True  # <--- ตั้งค่า Flag

    except Exception as e:
        print(f" Error: {e}")
        needs_refresh = False  # <--- ถ้า Error, ให้ข้ามการ Refresh

    # --- 2. ส่วนที่เพิ่มเข้ามา: ตรวจสอบ Flag และสั่ง Refresh ข้อมูล ---
    if needs_refresh:
        try:
            print(f"Post-config refresh: Running 'check_interface' for {router_ip}")
            output = get_interfaces(router_ip, router_username, router_password)
            save_interface_status(router_ip, output)
            print(f"Post-config refresh: Stored interface status for {router_ip}")
        except Exception as e:
            print(f" Post-config refresh FAILED: {e}")