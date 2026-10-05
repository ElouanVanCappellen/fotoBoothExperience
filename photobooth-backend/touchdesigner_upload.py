"""Paste ALL this file into a Text DAT named upload_api.
Same parent: Text TOP code_text, final Null TOP photo_out.
Trigger op('upload_api').module.take_photo(). No frame Execute DAT needed.
"""
import json
import queue
import secrets
import threading
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BACKEND_URL = 'http://127.0.0.1:8000'
_results = queue.Queue()
_busy = False
_code = None
_dat_path = me.path


def take_photo(new_session=True):
    """Called on the main TD thread. False adds another photo to the same code."""
    global _busy, _code
    if _busy:
        print('Wacht even: de vorige foto wordt nog verstuurd.')
        return
    text = op('code_text')
    final = op('photo_out')
    if text is None or final is None:
        raise RuntimeError('Maak code_text (Text TOP) en photo_out (Null TOP) naast upload_api.')
    if new_session or _code is None:
        _code = secrets.token_hex(6).upper()
    text.par.text = 'Jouw code: ' + _code
    _busy = True
    try:
        # Force the updated code to render before saving the final composite.
        text.cook(force=True)
        final.cook(force=True)
        path = Path(project.folder) / 'captures' / f'{_code}_{uuid.uuid4().hex}.png'
        final.save(str(path), asynchronous=False, createFolders=True)
    except Exception:
        _busy = False
        raise
    parent().store('photo_code', _code)
    parent().store('last_capture', str(path))
    print('Opname opgeslagen. Code:', _code)
    threading.Thread(target=_upload, args=(path, _code), daemon=True).start()
    _schedule_poll()
    return _code


def _upload(path, code):
    # No TouchDesigner operators are used on the background thread.
    try:
        request = Request(BACKEND_URL.rstrip('/') + '/api/photos', data=path.read_bytes(),
                          headers={'Content-Type': 'image/png', 'X-Photo-Code': code}, method='POST')
        with urlopen(request, timeout=90) as response:
            _results.put({'ok': True, **json.load(response)})
    except HTTPError as error:
        try:
            details = json.loads(error.read().decode())
        except Exception:
            details = {'error': 'Backend HTTP ' + str(error.code)}
        _results.put({**details, 'ok': False})
    except Exception as error:
        _results.put({'ok': False, 'error': str(error)})


def _schedule_poll():
    # TD's run(delayFrames=...) schedules this on its main thread.
    run(f"op({_dat_path!r}).module._poll()", delayFrames=10)


def _poll():
    global _busy
    try:
        result = _results.get_nowait()
    except queue.Empty:
        _schedule_poll()
        return
    _busy = False
    parent().store('upload_result', result)
    if result.get('ok'):
        parent().store('image_url', result['image_url'])
        parent().store('photo_url', result.get('page_url') or result['image_url'])
        print('ImageKit foto:', result['image_url'])
        print('Code:', result['code'])
        print('Website:', result.get('page_url'))
        print('Push docs/photos.json om de code op GitHub Pages beschikbaar te maken.')
    else:
        print('Upload mislukt:', result.get('error'))
        if result.get('image_url'):
            print('Foto is wel geüpload; bewaar deze link:', result['image_url'])
        print('De lokale opname blijft bewaard in captures.')
