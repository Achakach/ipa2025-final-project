from flask import Flask, request, render_template, redirect, url_for
import couchdb
import os
import time

sample = Flask(__name__)

# --- ฟังก์ชันสำหรับรอ CouchDB ---
def connect_to_couchdb():
    couchdb_uri = os.environ.get("COUCHDB_URI")
    for _ in range(10): # พยายามเชื่อมต่อ 10 ครั้ง
        try:
            server = couchdb.Server(couchdb_uri)
            # ตรวจสอบการเชื่อมต่อโดยการขอข้อมูล server
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
router_db_name = os.environ.get("ROUTER_DB_NAME")
interface_db_name = os.environ.get("INTERFACE_DB_NAME")

# สร้าง database ถ้ายังไม่มี
try:
    router_db = server.create(router_db_name)
except couchdb.PreconditionFailed:
    router_db = server[router_db_name]

try:
    interface_db = server.create(interface_db_name)
except couchdb.PreconditionFailed:
    interface_db = server[interface_db_name]

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
    all_docs = [interface_db.get(doc_id) for doc_id in interface_db]
    
    filtered_docs = [doc for doc in all_docs if doc and doc.get("router_ip") == ip]
    sorted_docs = sorted(filtered_docs, key=lambda x: x.get('timestamp', ''), reverse=True)
    limited_docs = sorted_docs[:3]
    
    return render_template("router_detail.html", router_ip=ip, interface_data=limited_docs)

if __name__ == "__main__":
    sample.run(host="0.0.0.0", port=8080)