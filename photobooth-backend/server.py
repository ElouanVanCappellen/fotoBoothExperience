"""Local photobooth upload server. Python 3, no dependencies."""
import argparse
import json
import uuid
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
STORE = ROOT / 'uploads'
MAX_SIZE = 15 * 1024 * 1024

PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Photobooth upload test</title>
<style>body{font:18px system-ui;max-width:680px;margin:60px auto;padding:24px;background:#111;color:#eee}button,input{font:inherit;margin:12px 0}button{padding:10px 20px}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#9cf}img{max-width:100%}</style>
<h1>Photobooth upload test</h1><p>Select a JPEG or PNG to test the same backend used by TouchDesigner.</p>
<form id="form"><input id="file" type="file" accept="image/jpeg,image/png" required><br><button>Upload photo</button></form>
<pre id="result"></pre><div id="preview"></div>
<script>document.querySelector('#form').onsubmit=async(e)=>{e.preventDefault();const out=document.querySelector('#result');out.textContent='Uploading…';try{const data=new FormData();data.append('image',document.querySelector('#file').files[0]);const r=await fetch('/api/photos',{method:'POST',body:data});const j=await r.json();out.textContent=JSON.stringify(j,null,2);const p=document.querySelector('#preview');p.replaceChildren();if(r.ok){const a=document.createElement('a');a.href=j.page_url;a.textContent='Open photo page';p.append(a);}}catch(err){out.textContent=String(err);}};</script></html>'''


class Handler(BaseHTTPRequestHandler):
    def send(self, status, body, content_type='application/json'):
        if isinstance(body, dict):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/':
            return self.send(200, PAGE, 'text/html; charset=utf-8')
        if path == '/health':
            return self.send(200, {'status': 'ok'})
        parts = path.strip('/').split('/')
        if len(parts) == 2 and parts[0] in ('photo', 'images'):
            photo_id = parts[1]
            if len(photo_id) != 32 or any(c not in '0123456789abcdef' for c in photo_id):
                return self.send(404, {'error': 'Photo not found'})
            files = list(STORE.glob(photo_id + '.*'))
            if not files:
                return self.send(404, {'error': 'Photo not found'})
            if parts[0] == 'photo':
                html = f'<!doctype html><html><meta name="viewport" content="width=device-width,initial-scale=1"><title>Your photo</title><body style="background:#111;color:white;font:18px system-ui;text-align:center;padding:24px"><h1>Your photobooth photo</h1><img style="max-width:100%;max-height:75vh" src="/images/{photo_id}"><p><a style="color:#9cf" href="/images/{photo_id}" download="photobooth{files[0].suffix}">Download photo</a></p></body></html>'
                return self.send(200, html, 'text/html; charset=utf-8')
            return self.send(200, files[0].read_bytes(), 'image/png' if files[0].suffix == '.png' else 'image/jpeg')
        self.send(404, {'error': 'Route not found'})

    def do_POST(self):
        self.upload()

    def do_PUT(self):
        self.upload()

    def upload(self):
        if urlsplit(self.path).path != '/api/photos':
            return self.send(404, {'error': 'Route not found'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return self.send(400, {'error': 'Invalid Content-Length'})
        if size <= 0 or size > MAX_SIZE:
            return self.send(413, {'error': 'Send an image body of at most 15 MB'})
        self.connection.settimeout(30)
        try:
            data = self.rfile.read(size)
        except TimeoutError:
            return self.send(408, {'error': 'Upload timed out'})
        if len(data) != size:
            return self.send(400, {'error': 'Incomplete upload'})
        content_type = self.headers.get('Content-Type', '')
        if content_type.startswith('multipart/form-data'):
            message = BytesParser(policy=default).parsebytes(('Content-Type: ' + content_type + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + data)
            if not message.is_multipart():
                return self.send(400, {'error': 'Invalid multipart upload'})
            matches = [p for p in message.iter_parts() if p.get_param('name', header='content-disposition') == 'image']
            if len(matches) != 1:
                return self.send(400, {'error': 'Use exactly one file field named image'})
            data = matches[0].get_payload(decode=True) or b''
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            extension = '.png'
        elif data.startswith(b'\xff\xd8\xff'):
            extension = '.jpg'
        else:
            return self.send(415, {'error': 'Only JPEG and PNG image data are accepted'})
        photo_id = uuid.uuid4().hex
        STORE.mkdir(exist_ok=True)
        (STORE / (photo_id + extension)).write_bytes(data)
        base = self.server.public_url
        self.send(201, {'photo_id': photo_id, 'page_url': base + '/photo/' + photo_id, 'image_url': base + '/images/' + photo_id})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--public-url', help='Base URL reachable by visitors, e.g. http://192.168.1.20:8000')
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.public_url = (args.public_url or f'http://localhost:{args.port}').rstrip('/')
    print(f'Photobooth backend ready: {server.public_url}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
