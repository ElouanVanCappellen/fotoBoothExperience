import os
import uuid
import base64
import json
from urllib.request import Request, urlopen

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


