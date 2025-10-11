import os
import couchdb


def get_router_info():
    couchdb_uri = os.environ.get("COUCHDB_URI")
    db_name = os.environ.get("ROUTER_DB_NAME")

    server = couchdb.Server(couchdb_uri)
    try:
        db = server[db_name]
    except couchdb.ResourceNotFound:
        return []

    router_data = [db.get(doc_id) for doc_id in db]
    return router_data


if __name__ == "__main__":
    get_router_info()
