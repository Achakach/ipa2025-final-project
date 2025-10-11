from datetime import datetime, UTC
import os
import couchdb


def save_interface_status(router_ip, interfaces):
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
        "interfaces": interfaces,
    }
    db.save(data)
