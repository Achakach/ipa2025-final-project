from netmiko import ConnectHandler
import ntc_templates
import os
import json


def get_interfaces(ip, username, password):
    os.environ["NET_TEXTFSM"] = os.path.join(
        os.path.dirname(ntc_templates.__file__), "templates"
    )
    device = {
        "device_type": "cisco_ios",
        "host": ip,
        "username": username,
        "password": password,
        "disabled_algorithms": dict(pubkeys=["rsa-sha2-512", "rsa-sha2-256"]),
    }
    with ConnectHandler(**device) as conn:
        conn.enable()
        result = conn.send_command("show ip int br", use_textfsm=True)
        conn.disconnect()
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    get_interfaces()
