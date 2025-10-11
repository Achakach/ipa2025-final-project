import json
from router_client import get_interfaces, backup_config  # <--- import ฟังก์ชันใหม่
from database import save_interface_status, save_backup_config  # <--- import ฟังก์ชันใหม่


def callback(ch, method, props, body):
    job = json.loads(body.decode())
    job_type = job.get("job_type", "check_interface")  # <--- กำหนดค่าเริ่มต้น

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

    except Exception as e:
        print(f" Error: {e}")
