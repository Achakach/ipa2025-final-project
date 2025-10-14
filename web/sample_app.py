from flask import Flask, request, render_template, redirect, url_for, Response
import couchdb
import os
import json
import pika
import time
import re
import ipaddress


sample = Flask(__name__)


# --- ฟังก์ชันสำหรับรอ CouchDB ---
def connect_to_couchdb():
    couchdb_uri = os.environ.get("COUCHDB_URI")
    for _ in range(10):
        try:
            server = couchdb.Server(couchdb_uri)
            server.version()
            print("Successfully connected to CouchDB.")
            return server
        except Exception as e:
            print(f"Failed to connect to CouchDB: {e}. Retrying in 5 seconds...")
            time.sleep(5)
    raise Exception("Could not connect to CouchDB after several attempts.")


server = connect_to_couchdb()
# --------------------------------

# ดึงชื่อ database จาก env
router_db_name = os.environ.get("ROUTER_DB_NAME", "my_routers_collection")
interface_db_name = os.environ.get("INTERFACE_DB_NAME", "interface_status")
backup_db_name = os.environ.get(
    "BACKUP_DB_NAME", "router_backups"
)  # <--- เพิ่ม DB สำหรับ backup

# สร้าง database ถ้ายังไม่มี
try:
    router_db = server.create(router_db_name)
except couchdb.PreconditionFailed:
    router_db = server[router_db_name]

try:
    interface_db = server.create(interface_db_name)
except couchdb.PreconditionFailed:
    interface_db = server[interface_db_name]

try:
    backup_db = server.create(backup_db_name)  # <--- สร้าง DB สำหรับ backup
except couchdb.PreconditionFailed:
    backup_db = server[backup_db_name]


@sample.route("/")
def main():
    items = [router_db.get(doc_id) for doc_id in router_db]
    return render_template("index.html", items=items)


@sample.route("/add", methods=["POST"])
def add_comment():
    ip = request.form.get("ip")
    user = request.form.get("user")
    password = request.form.get("password")
    if ip and user and password:
        router_db.save({"ip": ip, "user": user, "password": password})
    return redirect(url_for("main"))


@sample.route("/delete", methods=["POST"])
def delete_comment():
    doc_id = request.form.get("id")
    try:
        doc = router_db.get(doc_id)
        if doc:
            router_db.delete(doc)
    except Exception as e:
        print(f"Error deleting document: {e}")
    return redirect(url_for("main"))


@sample.route("/router/<ip>", methods=["GET"])
def router_detail(ip):
    # 1. ดึงข้อมูล Interface (เหมือนเดิม)
    all_interface_docs = [interface_db.get(doc_id) for doc_id in interface_db]
    filtered_interface_docs = [
        doc for doc in all_interface_docs if doc and doc.get("router_ip") == ip
    ]
    sorted_interface_docs = sorted(
        filtered_interface_docs, key=lambda x: x.get("timestamp", ""), reverse=True
    )
    latest_interface_data = None
    if sorted_interface_docs:
        latest_interface_data = sorted_interface_docs[0]
    # limited_interface_docs = sorted_interface_docs[:3]

    dhcp_raw_text = (
        latest_interface_data.get("dhcp_config_raw", "")
        if latest_interface_data
        else ""
    )
    dhcp_pools, excluded_addresses = parse_dhcp_pools(dhcp_raw_text)

    # 2. vvv ดึงข้อมูล Backup vvv
    all_backup_docs = [backup_db.get(doc_id) for doc_id in backup_db]
    filtered_backup_docs = [
        doc for doc in all_backup_docs if doc and doc.get("router_ip") == ip
    ]
    sorted_backup_docs = sorted(
        filtered_backup_docs, key=lambda x: x.get("timestamp", ""), reverse=True
    )

    # ดึงข้อมูล DNS จากเอกสารล่าสุด
    current_dns_servers = []
    if latest_interface_data and "dns_servers" in latest_interface_data:
        current_dns_servers = latest_interface_data["dns_servers"]

    return render_template(
        "router_detail.html",
        router_ip=ip,
        interface_data=latest_interface_data,
        backup_data=sorted_backup_docs,
        current_dns=current_dns_servers,
        dhcp_pools=dhcp_pools,
        dhcp_excluded=excluded_addresses,
    )


# --- ฟังก์ชันสำหรับส่ง message ไปยัง RabbitMQ ---
def send_to_rabbitmq(body):
    rabbitmq_user = os.getenv("RABBITMQ_DEFAULT_USER")
    rabbitmq_pass = os.getenv("RABBITMQ_DEFAULT_PASS")
    rabbitmq_host = os.getenv("RABBITMQ_HOST", "rabbitmq")

    credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_pass)
    parameters = pika.ConnectionParameters(rabbitmq_host, credentials=credentials)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    channel.queue_declare(queue="router_jobs")
    channel.basic_publish(exchange="", routing_key="router_jobs", body=body)
    connection.close()


@sample.route("/router/<ip>/backup", methods=["POST"])
def backup_router(ip):
    doc_to_backup = None
    for row in router_db.view("_all_docs", include_docs=True):
        if row.doc and row.doc.get("ip") == ip:
            doc_to_backup = row.doc
            break

    if doc_to_backup:
        job = {
            "job_type": "backup",
            "ip": doc_to_backup.get("ip"),
            "user": doc_to_backup.get("user"),
            "password": doc_to_backup.get("password"),
        }
        body_bytes = json.dumps(job).encode("utf-8")
        send_to_rabbitmq(body_bytes)

    return redirect(url_for("router_detail", ip=ip))


# vvv เพิ่ม Route นี้สำหรับ Download vvv
@sample.route("/backup/<backup_id>/download")
def download_backup(backup_id):
    backup_doc = backup_db.get(backup_id)
    if not backup_doc:
        return "Backup not found", 404

    config_text = backup_doc.get("config", "")
    router_ip = backup_doc.get("router_ip", "router")
    timestamp = backup_doc.get("timestamp", "").split("T")[0]  # เอาเฉพาะวันที่

    # สร้างชื่อไฟล์
    filename = f"backup-{router_ip}-{timestamp}.txt"

    # สร้าง Response เพื่อให้ browser ดาวน์โหลด
    return Response(
        config_text,
        mimetype="text/plain",
        headers={"Content-disposition": f"attachment; filename={filename}"},
    )


# ^^^ จบ Route ^^^


# vvv เพิ่ม Route นี้เข้าไป vvv
@sample.route("/backup/<backup_id>/view")
def view_backup(backup_id):
    backup_doc = backup_db.get(backup_id)
    if not backup_doc:
        return "Backup not found", 404

    # ส่งข้อมูล backup ทั้งหมดไปให้ template 'view_backup.html'
    return render_template("view_backup.html", backup=backup_doc)


# ^^^ จบส่วนที่เพิ่ม ^^^


# vvv เพิ่ม Route นี้เข้าไป vvv
@sample.route("/backup/<backup_id>/restore", methods=["POST"])
def restore_backup(backup_id):
    backup_doc = backup_db.get(backup_id)
    if not backup_doc:
        return "Backup not found", 404

    router_ip = backup_doc.get("router_ip")
    config_text = backup_doc.get("config")

    # ค้นหาข้อมูล credential ของเราเตอร์จาก DB
    router_info_doc = None
    for row in router_db.view("_all_docs", include_docs=True):
        if row.doc and row.doc.get("ip") == router_ip:
            router_info_doc = row.doc
            break

    if router_info_doc:
        # สร้าง "งาน" ที่มี job_type เป็น 'restore'
        job = {
            "job_type": "restore",
            "ip": router_ip,
            "user": router_info_doc.get("user"),
            "password": router_info_doc.get("password"),
            "config": config_text,  # <--- แนบเนื้อหา config ไปด้วย
        }
        body_bytes = json.dumps(job).encode("utf-8")
        send_to_rabbitmq(body_bytes)

    # หลังจากส่งงานแล้ว ให้ redirect กลับไปหน้ารายละเอียด
    return redirect(url_for("router_detail", ip=router_ip, status="restore_sent"))


# ^^^ จบ Route ^^^


@sample.route("/router/<ip>/interface/<interface_name>/config", methods=["GET", "POST"])
def config_interface(ip, interface_name):
    # แปลงชื่อ interface กลับ (ถ้าจำเป็น) - ในที่นี้เราใช้ชื่อตรงๆ
    interface_name_full = interface_name.replace("-", "/")

    if request.method == "POST":
        # รับข้อมูลจากฟอร์ม
        config_type = request.form.get("config_type")

        job = {
            "job_type": "configure_interface",
            "ip": ip,
            "interface_name": interface_name_full,
            "config_type": config_type,
        }

        # ค้นหา Credential
        router_info_doc = None
        for row in router_db.view("_all_docs", include_docs=True):
            if row.doc and row.doc.get("ip") == ip:
                router_info_doc = row.doc
                break

        if not router_info_doc:
            return "Router credentials not found", 404

        job["user"] = router_info_doc.get("user")
        job["password"] = router_info_doc.get("password")

        if config_type == "manual":
            job["ip_address"] = request.form.get("ip_address")
            job["subnet_prefix"] = request.form.get("subnet_prefix")

        body_bytes = json.dumps(job).encode("utf-8")
        send_to_rabbitmq(body_bytes)

        # ส่งกลับไปหน้ารายละเอียดพร้อม pop-up
        return redirect(url_for("router_detail", ip=ip, status="config_sent"))

    # ถ้าเป็น GET request, แสดงฟอร์ม
    return render_template(
        "config_interface.html", router_ip=ip, interface_name=interface_name_full
    )


@sample.route("/router/<ip>/dns", methods=["GET", "POST"])
def config_dns(ip):
    if request.method == "POST":
        dns1 = request.form.get("dns_server_1")
        dns2 = request.form.get("dns_server_2")

        job = {"job_type": "configure_dns", "ip": ip, "dns_servers": [dns1, dns2]}

        # ค้นหา Credential
        router_info_doc = None
        for row in router_db.view("_all_docs", include_docs=True):
            if row.doc and row.doc.get("ip") == ip:
                router_info_doc = row.doc
                break

        if not router_info_doc:
            return "Router credentials not found", 404

        job["user"] = router_info_doc.get("user")
        job["password"] = router_info_doc.get("password")

        body_bytes = json.dumps(job).encode("utf-8")
        send_to_rabbitmq(body_bytes)

        # ส่งกลับไปหน้ารายละเอียดพร้อม pop-up
        return redirect(url_for("router_detail", ip=ip, status="dns_config_sent"))

    # ถ้าเป็น GET request, แสดงฟอร์ม
    return render_template("config_dns.html", router_ip=ip)


@sample.route("/router/<ip>/dns/delete", methods=["POST"])
def delete_dns_server(ip):
    dns_to_delete = request.form.get("dns_server")

    job = {
        "job_type": "delete_dns",
        "ip": ip,
        "dns_server": dns_to_delete,
    }

    # ค้นหา Credential
    router_info_doc = None
    for row in router_db.view("_all_docs", include_docs=True):
        if row.doc and row.doc.get("ip") == ip:
            router_info_doc = row.doc
            break

    if not router_info_doc:
        return "Router credentials not found", 404

    job["user"] = router_info_doc.get("user")
    job["password"] = router_info_doc.get("password")

    body_bytes = json.dumps(job).encode("utf-8")
    send_to_rabbitmq(body_bytes)

    # ส่งกลับไปหน้ารายละเอียดพร้อม pop-up
    return redirect(url_for("router_detail", ip=ip, status="dns_delete_sent"))


@sample.route("/router/<ip>/dhcp", methods=["GET", "POST"])
def config_dhcp(ip):
    if request.method == "POST":
        # 1. ดึงข้อมูลจากฟอร์ม
        job = {
            "job_type": "configure_dhcp",
            "ip": ip,
            "pool_name": request.form.get("pool_name"),
            "network_address": request.form.get("network_address"),
            "subnet_prefix": request.form.get("subnet_prefix"),
            "default_gateway": request.form.get("default_gateway"),
            "exclude_start_ip": request.form.get("exclude_start_ip"),
            "exclude_end_ip": request.form.get("exclude_end_ip"),
            "dns_servers": [
                request.form.get("dns_server_1"),
                request.form.get("dns_server_2"),
            ],
        }

        # 2. ค้นหา Credential ของ Router
        router_info_doc = None
        for row in router_db.view("_all_docs", include_docs=True):
            if row.doc and row.doc.get("ip") == ip:
                router_info_doc = row.doc
                break

        if not router_info_doc:
            return "Router credentials not found", 404

        job["user"] = router_info_doc.get("user")
        job["password"] = router_info_doc.get("password")

        # 3. ส่ง Job ไปที่ RabbitMQ
        body_bytes = json.dumps(job).encode("utf-8")
        send_to_rabbitmq(body_bytes)

        # 4. Redirect กลับไปพร้อม Alert
        # เราจะสร้าง status ใหม่ชื่อ 'dhcp_config_sent'
        return redirect(url_for("router_detail", ip=ip, status="dhcp_config_sent"))

    # ถ้าเป็น GET request, แสดงฟอร์ม
    return render_template("config_dhcp.html", router_ip=ip)


def parse_dhcp_pools(raw_config):
    """
    แปลง raw config string ของ DHCP ให้เป็น list of dictionaries
    """
    if not raw_config:
        return [], []

    pools = {}
    excluded_addresses = []

    # แยก excluded addresses ออกมาก่อน
    for line in raw_config.splitlines():
        if line.startswith("ip dhcp excluded-address"):
            parts = line.split()
            if len(parts) >= 4:
                excluded_addresses.append(
                    f"{parts[3]} - {parts[4] if len(parts) > 4 else ''}"
                )

    # หา pool และค่า config ภายใน
    current_pool = None
    for line in raw_config.splitlines():
        pool_match = re.match(r"^ip dhcp pool\s+(.+)", line)
        if pool_match:
            current_pool = pool_match.group(1).strip()
            pools[current_pool] = {"name": current_pool}
            continue

        if current_pool and line.startswith(" "):
            parts = line.strip().split()
            if parts[0] == "network" and len(parts) >= 3:
                pools[current_pool]["network"] = f"{parts[1]} / {parts[2]}"
            elif parts[0] == "default-router" and len(parts) >= 2:
                pools[current_pool]["default_router"] = parts[1]
            elif parts[0] == "dns-server" and len(parts) >= 2:
                pools[current_pool]["dns_servers"] = " ".join(parts[1:])

    return list(pools.values()), excluded_addresses


@sample.route("/router/<ip>/dhcp/delete", methods=["POST"])
def delete_dhcp(ip):
    pool_name = request.form.get("pool_name")

    job = {
        "job_type": "delete_dhcp_pool",
        "ip": ip,
        "pool_name": pool_name,
    }

    # ค้นหา Credential
    router_info_doc = None
    for row in router_db.view("_all_docs", include_docs=True):
        if row.doc and row.doc.get("ip") == ip:
            router_info_doc = row.doc
            break

    if not router_info_doc:
        return "Router credentials not found", 404

    job["user"] = router_info_doc.get("user")
    job["password"] = router_info_doc.get("password")

    body_bytes = json.dumps(job).encode("utf-8")
    send_to_rabbitmq(body_bytes)

    # ส่งกลับไปหน้ารายละเอียดพร้อม pop-up
    return redirect(url_for("router_detail", ip=ip, status="dhcp_delete_sent"))


@sample.route("/router/<ip>/dhcp/edit/<pool_name>", methods=["GET", "POST"])
def edit_dhcp(ip, pool_name):
    # --- จัดการเมื่อผู้ใช้กด "Apply Changes" ---
    if request.method == "POST":
        # 1. สร้าง Job สำหรับ "ลบ" Pool เก่า
        delete_job = {"job_type": "delete_dhcp_pool", "ip": ip, "pool_name": pool_name}

        # 2. สร้าง Job สำหรับ "สร้าง" Pool ใหม่ด้วยข้อมูลจากฟอร์ม
        # (ใช้ Logic เดียวกับฟังก์ชัน config_dhcp)
        create_job = {
            "job_type": "configure_dhcp",
            "ip": ip,
            "pool_name": request.form.get("pool_name"),  # ซึ่งเป็นชื่อเดิม
            "network_address": request.form.get("network_address"),
            "subnet_prefix": request.form.get("subnet_prefix"),
            "default_gateway": request.form.get("default_gateway"),
            "dns_servers": [
                request.form.get("dns_server_1"),
                request.form.get("dns_server_2"),
            ],
            "exclude_start_ip": "",  # ไม่จัดการ Exclude ในหน้า Edit
            "exclude_end_ip": "",
        }

        # 3. ค้นหา Credential (ทำครั้งเดียวพอ)
        router_info_doc = None
        for row in router_db.view("_all_docs", include_docs=True):
            if row.doc and row.doc.get("ip") == ip:
                router_info_doc = row.doc
                break
        if not router_info_doc:
            return "Router credentials not found", 404

        delete_job["user"] = create_job["user"] = router_info_doc.get("user")
        delete_job["password"] = create_job["password"] = router_info_doc.get(
            "password"
        )

        # 4. ส่ง Job ทั้งสองไปที่ RabbitMQ (ลบก่อนสร้าง)
        send_to_rabbitmq(json.dumps(delete_job).encode("utf-8"))
        send_to_rabbitmq(json.dumps(create_job).encode("utf-8"))

        return redirect(url_for("router_detail", ip=ip, status="dhcp_edit_sent"))

    # --- จัดการเมื่อผู้ใช้กดปุ่ม "Edit" เพื่อแสดงฟอร์ม ---
    # 1. ดึงข้อมูลล่าสุดจาก DB
    all_interface_docs = [interface_db.get(doc_id) for doc_id in interface_db]
    filtered_docs = [
        doc for doc in all_interface_docs if doc and doc.get("router_ip") == ip
    ]
    latest_doc = sorted(
        filtered_docs, key=lambda x: x.get("timestamp", ""), reverse=True
    )[0]
    dhcp_raw_text = latest_doc.get("dhcp_config_raw", "") if latest_doc else ""

    # 2. Parse หา Pool ที่ต้องการแก้ไข
    all_pools, _ = parse_dhcp_pools(dhcp_raw_text)
    pool_to_edit = next(
        (pool for pool in all_pools if pool.get("name") == pool_name), None
    )
    if not pool_to_edit:
        return "DHCP Pool not found", 404

    # 3. เตรียมข้อมูลสำหรับ pre-fill ในฟอร์ม
    network_parts = pool_to_edit.get("network", " / ").split(" / ")
    pool_to_edit["network_address"] = network_parts[0]
    try:
        pool_to_edit["subnet_prefix"] = ipaddress.IPv4Network(
            f"0.0.0.0/{network_parts[1]}"
        ).prefixlen
    except Exception:
        pool_to_edit["subnet_prefix"] = 24  # Fallback

    dns_list = pool_to_edit.get("dns_servers", "").split()
    pool_to_edit["dns_server_1"] = dns_list[0] if len(dns_list) > 0 else ""
    pool_to_edit["dns_server_2"] = dns_list[1] if len(dns_list) > 1 else ""

    return render_template("edit_dhcp.html", router_ip=ip, pool=pool_to_edit)


@sample.route("/router/<ip>/save", methods=["POST"])
def save_configuration(ip):
    job = {"job_type": "save_config", "ip": ip}

    # ค้นหา Credential
    router_info_doc = None
    for row in router_db.view("_all_docs", include_docs=True):
        if row.doc and row.doc.get("ip") == ip:
            router_info_doc = row.doc
            break

    if not router_info_doc:
        return "Router credentials not found", 404

    job["user"] = router_info_doc.get("user")
    job["password"] = router_info_doc.get("password")

    body_bytes = json.dumps(job).encode("utf-8")
    send_to_rabbitmq(body_bytes)

    # ส่งกลับไปหน้ารายละเอียดพร้อม pop-up
    return redirect(url_for("router_detail", ip=ip, status="save_sent"))

@sample.route("/router/<ip>/acl", methods=["GET", "POST"])
def config_acl(ip):
    if request.method == "POST":
        # 1. แยก Rules ออกจากข้อมูล Form อื่นๆ
        rules = []
        # ใช้ regex เพื่อหา key ทั้งหมดที่ตรงกับรูปแบบของ rule (เช่น action_1, source_ip_1)
        rule_keys = [key for key in request.form if re.match(r"action_\d+", key)]
        for key in rule_keys:
            # ดึงหมายเลข rule จาก key (เช่น 'action_1' -> '1')
            rule_num = key.split('_')[1]
            rule = {
                "action": request.form.get(f"action_{rule_num}"),
                "source_ip": request.form.get(f"source_ip_{rule_num}"),
                "wildcard": request.form.get(f"wildcard_{rule_num}"),
            }
            rules.append(rule)

        # 2. สร้าง Job
        job = {
            "job_type": "configure_acl",
            "ip": ip,
            "acl_number": request.form.get("acl_number"),
            "rules": rules,
            "interface_name": request.form.get("interface_name"),
            "direction": request.form.get("direction"),
        }

        # 3. ค้นหา Credential และส่ง Job (เหมือนเดิม)
        router_info_doc = None
        for row in router_db.view("_all_docs", include_docs=True):
            if row.doc and row.doc.get("ip") == ip:
                router_info_doc = row.doc
                break
        if not router_info_doc: return "Router credentials not found", 404

        job["user"] = router_info_doc.get("user")
        job["password"] = router_info_doc.get("password")

        body_bytes = json.dumps(job).encode("utf-8")
        send_to_rabbitmq(body_bytes)

        return redirect(url_for("router_detail", ip=ip, status="acl_config_sent"))

    # GET request
    return render_template("config_acl.html", router_ip=ip)


if __name__ == "__main__":
    sample.run(host="0.0.0.0", port=8080)
