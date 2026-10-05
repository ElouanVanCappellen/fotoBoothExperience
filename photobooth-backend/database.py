import os
from datetime import datetime, timezone
from pymongo import MongoClient


def connect():
    uri = os.environ.get('MONGODB_URI', '').strip()
    if not uri:
        raise RuntimeError('Set MONGODB_URI in the environment')
    client = MongoClient(uri, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000,
                         socketTimeoutMS=20000)
    try:
        client.admin.command('ping')
    except Exception:
        client.close()
        raise RuntimeError('MongoDB connection failed. Check URI, database user and Atlas Network Access.') from None
    collection = client[os.environ.get('MONGODB_DB', 'photobooth')]['sessions']
    return client, collection


def save_image(collection, code, image):
    # _id is the unique session code; one atomic update, no read/modify/write race.
    collection.update_one({'_id': code}, {
        '$setOnInsert': {'code': code, 'created_at': datetime.now(timezone.utc).isoformat()},
        '$addToSet': {'images': image}
    }, upsert=True)


def find_session(collection, code):
    return collection.find_one({'_id': code}, {'_id': 0, 'code': 1, 'images': 1, 'created_at': 1})

