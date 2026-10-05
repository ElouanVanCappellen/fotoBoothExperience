"""One-time, repeatable import. Original JSON is never changed."""
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from database import connect, save_image


def prepare(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or not isinstance(data.get('sessions'), list):
        raise ValueError('JSON must contain a sessions array')
    records = []
    for session in data['sessions']:
        if not isinstance(session, dict):
            raise ValueError('Invalid session')
        if session.get('demo'):
            continue
        code = str(session.get('code', '')).strip().upper()
        if not re.fullmatch(r'[A-Z0-9-]{4,64}', code) or not isinstance(session.get('images'), list):
            raise ValueError('Each session needs a valid code and images array')
        for item in session['images']:
            item = {'url': item} if isinstance(item, str) else item
            if not isinstance(item, dict) or not isinstance(item.get('url'), str):
                raise ValueError('Invalid image record')
            url = urlsplit(item['url'])
            if url.scheme != 'https' or not url.netloc:
                raise ValueError('Real image links must be absolute HTTPS URLs')
            image = {'url': item['url']}
            # Canonical order and fields make repeated imports deduplicate.
            for field in ('imagekit_file_id', 'caption'):
                if isinstance(item.get(field), str):
                    image[field] = item[field]
            records.append((code, image))
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('json_path', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        records = prepare(args.json_path)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(f'{len(records)} images across {len(set(code for code, _ in records))} sessions. Demo sessions skipped.')
    if not args.dry_run:
        client, collection = connect()
        try:
            for code, image in records:
                save_image(collection, code, image)
        finally:
            client.close()
        print('Import completed. Original JSON preserved. Repeating the same import does not duplicate records.')

