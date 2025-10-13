from datetime import datetime, UTC
import os
import couchdb


def save_interface_status(router_ip, status_data):
    couchdb_uri = os.getenv("COUCHDB_URI")
    db_name = os.getenv("INTERFACE_DB_NAME")

    server = couchdb.Server(couchdb_uri)
    try:
        db = server[db_name]
    except couchdb.ResourceNotFound:
        db = server.create(db_name)

    data = {
        "router_ip": router_ip,
        "timestamp": datetime.now(UTC).isoformat(),
        "interfaces": status_data.get("interfaces", []),
        "dns_servers": status_data.get("dns_servers", []),
    }
    db.save(data)


def save_backup_config(router_ip, config_text):
    """บันทึก config ที่ได้จากการ backup ลงใน DB"""
    couchdb_uri = os.getenv("COUCHDB_URI")
    # เราจะใช้ DB ใหม่ชื่อ 'router_backups'
    db_name = os.getenv("BACKUP_DB_NAME", "router_backups")

    server = couchdb.Server(couchdb_uri)
    try:
        db = server[db_name]
    except couchdb.ResourceNotFound:
        db = server.create(db_name)

    data = {
        "router_ip": router_ip,
        "timestamp": datetime.now(UTC).isoformat(),
        "config": config_text,
    }
    db.save(data)
