import json # <--- เปลี่ยนจาก bson
from router_client import get_interfaces
from database import save_interface_status

def callback(ch, method, props, body):
    # vvv เปลี่ยนมาใช้ json.loads vvv
    job = json.loads(body.decode())
    router_ip = job["ip"]
    router_username = job["user"]
    router_password = job["password"]
    print(f"Received job for router {router_ip}")

    try:
        output = get_interfaces(router_ip, router_username, router_password)
        save_interface_status(router_ip, output)
        print(f"Stored interface status for {router_ip}")
    except Exception as e:
        print(f" Error: {e}")