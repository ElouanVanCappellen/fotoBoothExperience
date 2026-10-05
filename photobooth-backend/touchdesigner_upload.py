"""Run in a TouchDesigner Text DAT after saving your final TOP as a PNG.
Call upload_photo('/absolute/path/to/photo.png') from your capture callback.
Upload runs off the main thread. A frame callback can call poll_upload().
"""
import json
import queue
import threading
import urllib.request
from pathlib import Path

BACKEND_URL = 'http://127.0.0.1:8000'
results = queue.Queue()


def upload_photo(file_path):
    def worker():
        try:
            path = Path(file_path)
            request = urllib.request.Request(
                BACKEND_URL + '/api/photos', data=path.read_bytes(),
                headers={'Content-Type': 'application/octet-stream'}, method='POST')
            with urllib.request.urlopen(request, timeout=30) as response:
                results.put({'ok': True, **json.load(response)})
        except Exception as error:
            results.put({'ok': False, 'error': str(error)})
    threading.Thread(target=worker, daemon=True).start()


def poll_upload():
    """Call on the main TouchDesigner thread; None means still waiting."""
    try:
        return results.get_nowait()
    except queue.Empty:
        return None
