"""Local TouchDesigner -> ImageKit bridge. Python 3, no extra packages.
Set IMAGEKIT_PRIVATE_KEY in the environment before starting.
Default JSON output: ../docs/photos.json relative to this file.
"""
import argparse
import base64
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MAX_SIZE = 15 * 1024 * 1024
LOCK = threading.Lock()
CODE_PATTERN = re.compile(r'[A-Z0-9-]{4,64}')


def upload_image(data, extension, code):
    key = os.environ.get('IMAGEKIT_PRIVATE_KEY', '').strip()
    if not key:
        raise RuntimeError('Set IMAGEKIT_PRIVATE_KEY before starting the server')
    boundary = 'booth' + uuid.uuid4().hex
    filename = f'{code}_{uuid.uuid4().hex}{extension}'
    body = bytearray()
    for name, value in [('fileName', filename), ('folder', '/photobooth'), ('useUniqueFileName', 'true')]:
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    mime = 'image/png' if extension == '.png' else 'image/jpeg'
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode())
    body.extend(data)
    body.extend(f'\r\n--{boundary}--\r\n'.encode())
    credentials = base64.b64encode((key + ':').encode()).decode()
    request = Request('https://upload.imagekit.io/api/v1/files/upload',
                      data=bytes(body), method='POST', headers={
                          'Authorization': 'Basic ' + credentials,
                          'Content-Type': 'multipart/form-data; boundary=' + boundary})
    with urlopen(request, timeout=60) as response:
        result = json.load(response)
    if not isinstance(result.get('url'), str) or not result.get('fileId'):
        raise RuntimeError('ImageKit returned no image URL or file ID')
    return result


def save_photo(path, code, image):
    """Serialize writes and atomically replace JSON; preserve other sessions."""
    with LOCK:
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'sessions': []}
        if not isinstance(data, dict) or not isinstance(data.get('sessions'), list):
            raise ValueError('photos.json must contain a sessions array')
        sessions = data['sessions']
        if any(not isinstance(s, dict) or not isinstance(s.get('images'), list) for s in sessions):
            raise ValueError('Every session must contain an images array')
        session = next((s for s in sessions if str(s.get('code', '')).upper() == code), None)
        if session is None:
            session = {'code': code, 'created_at': datetime.now(timezone.utc).isoformat(), 'images': []}
            sessions.append(session)
        session['images'].append({'url': image['url'], 'imagekit_file_id': image['fileId'],
                                  'caption': f"Foto {len(session['images']) + 1:02d}"})
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.tmp')
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        os.replace(temporary, path)


class Handler(BaseHTTPRequestHandler):
    def send(self, status, data):
        payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if urlsplit(self.path).path == '/health':
            return self.send(200, {'status': 'ok', 'imagekit_configured': bool(os.environ.get('IMAGEKIT_PRIVATE_KEY'))})
        self.send(404, {'error': 'Route not found'})

    def do_POST(self):
        if urlsplit(self.path).path != '/api/photos':
            return self.send(404, {'error': 'Route not found'})
        code = self.headers.get('X-Photo-Code', '').strip().upper()
        if not CODE_PATTERN.fullmatch(code):
            return self.send(400, {'error': 'Send X-Photo-Code: 4-64 letters, numbers or hyphens'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.send(400, {'error': 'Invalid Content-Length'})
        if not 0 < size <= MAX_SIZE:
            return self.send(413, {'error': 'Image must be between 1 byte and 15 MB'})
        self.connection.settimeout(30)
        try:
            data = self.rfile.read(size)
        except TimeoutError:
            return self.send(408, {'error': 'Upload timed out'})
        if len(data) != size:
            return self.send(400, {'error': 'Incomplete upload'})
        extension = '.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if data.startswith(b'\xff\xd8\xff') else None
        if extension is None:
            return self.send(415, {'error': 'Send raw PNG or JPEG image bytes'})
        try:
            image = upload_image(data, extension, code)
        except HTTPError as error:
            return self.send(502, {'error': f'ImageKit rejected the upload (HTTP {error.code}); check your private key and account limits'})
        except (URLError, TimeoutError):
            return self.send(502, {'error': 'Could not reach ImageKit; check the internet connection'})
        except Exception as error:
            return self.send(500, {'error': str(error)})
        try:
            save_photo(self.server.json_path, code, image)
        except Exception as error:
            # Return the successful upload details so the link can be recovered.
            return self.send(500, {'error': 'Image uploaded, but JSON could not be saved: ' + str(error),
                                   'code': code, 'image_url': image['url'], 'imagekit_file_id': image['fileId']})
        page = self.server.frontend_url + '?code=' + code if self.server.frontend_url else None
        self.send(201, {'code': code, 'image_url': image['url'], 'imagekit_file_id': image['fileId'],
                        'page_url': page, 'json_saved': True,
                        'note': 'Push photos.json and wait for Pages deployment before using page_url'})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--json', default=str(Path(__file__).resolve().parent.parent / 'docs' / 'photos.json'))
    parser.add_argument('--frontend-url', default='https://elouanvancappellen.github.io/fotoBoothExperience/')
    args = parser.parse_args()
    if not os.environ.get('IMAGEKIT_PRIVATE_KEY', '').strip():
        parser.error('Set the IMAGEKIT_PRIVATE_KEY environment variable first. Never commit it to GitHub.')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.json_path = Path(args.json).resolve()
    server.frontend_url = args.frontend_url
    print(f'Backend: http://127.0.0.1:{args.port}\nJSON: {server.json_path}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
