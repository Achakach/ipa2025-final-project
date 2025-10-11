import ansible_runner
import os
import json


def get_interfaces(ip, username, password):
    private_data_dir = os.path.dirname(__file__)

    inventory = {"all": {"hosts": {ip: None}}}

    result = ansible_runner.run(
        private_data_dir=private_data_dir,
        playbook="playbook.yml",
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


if __name__ == "__main__":
    pass
