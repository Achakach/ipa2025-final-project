from flask import Flask, request, render_template, redirect, url_for, Response
import couchdb
import os
import json
import pika
import time

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
    limited_interface_docs = sorted_interface_docs[:3]

    # 2. vvv ดึงข้อมูล Backup vvv
    all_backup_docs = [backup_db.get(doc_id) for doc_id in backup_db]
    filtered_backup_docs = [
        doc for doc in all_backup_docs if doc and doc.get("router_ip") == ip
    ]
    sorted_backup_docs = sorted(
        filtered_backup_docs, key=lambda x: x.get("timestamp", ""), reverse=True
    )

    return render_template(
        "router_detail.html",
        router_ip=ip,
        interface_data=limited_interface_docs,
        backup_data=sorted_backup_docs,  # <--- ส่งรายการ backup ไปที่หน้าเว็บ
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


if __name__ == "__main__":
    sample.run(host="0.0.0.0", port=8080)
