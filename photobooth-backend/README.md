# Photobooth test backend

Requires Python 3. No packages to install.

## Start

Open a terminal in this folder and run:

```sh
python3 server.py
```

Open http://localhost:8000 to upload a photo manually. Stop with Ctrl+C.

## Upload API

`POST /api/photos` or `PUT /api/photos` accepts:

- Raw PNG/JPEG bytes (ideal for TouchDesigner).
- Multipart form data with one file field named `image` (browser test).

Maximum request size: 15 MB. Success returns HTTP 201:

```json
{"photo_id":"random32characterid", "page_url":"http://localhost:8000/photo/...", "image_url":"http://localhost:8000/images/..."}
```

Use `page_url` for the ticket QR code. `GET /health` returns server status.
Photos persist in `uploads/` next to the server across restarts.

Terminal test, replacing the file path:

```sh
curl -X POST http://localhost:8000/api/photos -H 'Content-Type: image/png' --data-binary @photo.png
```

## TouchDesigner

Paste `touchdesigner_upload.py` into a Text DAT named `upload_api`.
Once the processed image has been saved to disk, call:

```python
op('upload_api').module.upload_photo('/absolute/path/to/photo.png')
```

From an Execute DAT's frame callback, poll for completion:

```python
def onFrameStart(frame):
    result = op('upload_api').module.poll_upload()
    if result is not None:
        if result['ok']:
            print('Photo ready:', result['page_url'])
            # Use this URL for the QR code and then print the ticket.
        else:
            print('Upload failed:', result['error'])
    return
```

Enable Frame Start on that Execute DAT. Keep TouchDesigner operators and printer
actions in the main-thread callback. The upload worker only handles the file/network.

## Test from a phone on the same Wi-Fi

Find the computer's local network IP in its network settings. For example:

```sh
python3 server.py --host 0.0.0.0 --public-url http://192.168.1.20:8000
```

Replace the example IP with yours, then open that address on your phone.
Allow incoming connections if the firewall prompts. If TouchDesigner is on a
different computer, change BACKEND_URL in the upload script to that address too.

This is a local development server: localhost links only work on the same computer;
Wi-Fi links only work on that network. Public hosting, HTTPS, upload authentication,
full image decoding/validation, and photo retention rules are needed before a public
deployment. File signatures are checked here; images are not fully decoded.
