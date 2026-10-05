"""Same TouchDesigner upload endpoint, now with MongoDB and a public lookup API."""
import argparse
import asyncio
import os
import re
from contextlib import asynccontextmanager
from urllib.error import HTTPError, URLError

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from database import connect, find_session, save_image
from imagekit_upload import upload_image

MAX_SIZE = 15 * 1024 * 1024
CODE = re.compile(r'[A-Z0-9-]{4,64}')


@asynccontextmanager
async def lifespan(app):
    client, collection = await asyncio.to_thread(connect)
    app.state.collection = collection
    try:
        yield
    finally:
        client.close()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)
origins = [s.strip() for s in os.environ.get('FRONTEND_ORIGINS',
           'https://elouanvancappellen.github.io,http://localhost:8080').split(',') if s.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=['GET'], allow_headers=[])


def reply(status, body):
    return JSONResponse(body, status_code=status, headers={'Cache-Control': 'no-store'})


@app.get('/health')
def health():
    # Startup already pings MongoDB; check it again for current health.
    try:
        app.state.collection.database.client.admin.command('ping')
    except Exception:
        return reply(503, {'status': 'error', 'mongodb_connected': False})
    return reply(200, {'status': 'ok', 'mongodb_connected': True,
                       'imagekit_configured': bool(os.environ.get('IMAGEKIT_PRIVATE_KEY'))})


@app.get('/api/photos/{code}')
def lookup(code: str):
    code = code.strip().upper()
    if not CODE.fullmatch(code):
        return reply(400, {'error': 'Invalid code'})
    try:
        session = find_session(app.state.collection, code)
    except Exception:
        return reply(503, {'error': 'Database temporarily unavailable'})
    return reply(200, session) if session else reply(404, {'error': 'Code not found'})


@app.post('/api/photos')
async def upload(request: Request):
    # Local bridge permits loopback only. Hosted API is read-only by default.
    if not getattr(app.state, 'local_uploads', False):
        return reply(403, {'error': 'This hosted API is read-only; upload through the local booth backend'})
    if not request.client or request.client.host not in ('127.0.0.1', '::1'):
        return reply(403, {'error': 'Uploads are only allowed from this computer'})
    code = request.headers.get('X-Photo-Code', '').strip().upper()
    if not CODE.fullmatch(code):
        return reply(400, {'error': 'Send a valid X-Photo-Code header'})
    if not os.environ.get('IMAGEKIT_PRIVATE_KEY'):
        return reply(503, {'error': 'Set IMAGEKIT_PRIVATE_KEY in the local backend environment'})
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_SIZE:
            return reply(413, {'error': 'Maximum image size is 15 MB'})
        body.extend(chunk)
    data = bytes(body)
    extension = '.png' if data.startswith(b'\x89PNG\r\n\x1a\n') else '.jpg' if data.startswith(b'\xff\xd8\xff') else None
    if extension is None:
        return reply(415, {'error': 'Send raw PNG or JPEG bytes'})
    try:
        image = await asyncio.to_thread(upload_image, data, extension, code)
    except HTTPError as error:
        return reply(502, {'error': f'ImageKit rejected upload (HTTP {error.code})'})
    except (URLError, TimeoutError):
        return reply(502, {'error': 'Could not reach ImageKit'})
    except Exception:
        return reply(502, {'error': 'ImageKit upload failed; check your private key and account'})
    record = {'url': image['url'], 'imagekit_file_id': image['fileId']}
    try:
        await asyncio.to_thread(save_image, app.state.collection, code, record)
    except Exception:
        return reply(503, {'error': 'Image uploaded but database save failed; keep this link to recover it',
                           'code': code, 'image_url': image['url'], 'imagekit_file_id': image['fileId']})
    frontend = os.environ.get('FRONTEND_URL', 'https://elouanvancappellen.github.io/fotoBoothExperience/')
    return reply(201, {'code': code, 'image_url': image['url'], 'imagekit_file_id': image['fileId'],
                       'page_url': frontend + '?code=' + code, 'mongodb_saved': True})


if __name__ == '__main__':
    import uvicorn
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    app.state.local_uploads = True
    uvicorn.run(app, host='127.0.0.1', port=args.port)

