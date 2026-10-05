// Same-folder JSON works on GitHub Pages project URLs as well as custom domains.
const DATA_URL = new URL('photos.json', document.baseURI);
const form = document.querySelector('#lookup');
const input = document.querySelector('#code');
const button = document.querySelector('#submit');
const status = document.querySelector('#status');
const results = document.querySelector('#results');
const gallery = document.querySelector('#gallery');
const normalizeCode = value => String(value).trim().toUpperCase();

function imageURL(value) {
  if (typeof value !== 'string' || !value.trim()) throw new Error('invalid-image');
  const url = new URL(value, document.baseURI);
  if (!['https:', 'http:'].includes(url.protocol)) throw new Error('invalid-image');
  return url.href;
}

function showStatus(message, error = false) {
  status.textContent = message;
  status.dataset.error = String(error);
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const code = normalizeCode(input.value);
  results.hidden = true;
  gallery.replaceChildren();
  if (!/^[A-Z0-9-]{4,64}$/.test(code)) {
    showStatus('Vul een code van 4 tot 64 letters, cijfers of streepjes in.', true);
    input.focus();
    return;
  }
  button.disabled = true;
  input.disabled = true;
  form.setAttribute('aria-busy', 'true');
  showStatus('Even zoeken naar jouw moment…');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const url = new URL(DATA_URL);
    url.searchParams.set('v', Date.now());
    const response = await fetch(url, { cache: 'no-store', signal: controller.signal });
    if (!response.ok) throw new Error('load');
    const data = await response.json();
    if (!Array.isArray(data.sessions)) throw new Error('schema');
    const session = data.sessions.find(item => item && normalizeCode(item.code) === code);
    if (!session) {
      showStatus('Deze code is nog niet gevonden. Controleer je ticket of probeer het straks opnieuw.', true);
      return;
    }
    if (!Array.isArray(session.images)) throw new Error('schema');
    if (!session.images.length) {
      showStatus('Je foto’s worden nog klaargemaakt. Probeer het zo opnieuw.');
      return;
    }
    const photos = session.images.map(image => ({
      url: imageURL(typeof image === 'string' ? image : image.url),
      caption: typeof image === 'object' && typeof image.caption === 'string' ? image.caption : null
    }));
    photos.forEach((photo, index) => {
      const card = document.createElement('figure');
      card.className = 'photo-card';
      const img = document.createElement('img');
      img.src = photo.url;
      img.alt = photo.caption || `Jouw photoboothfoto ${index + 1}`;
      img.loading = 'lazy';
      img.addEventListener('error', () => {
        img.hidden = true;
        const error = document.createElement('p');
        error.className = 'photo-error';
        error.textContent = 'Deze foto kon niet laden. Probeer de fotolink hieronder.';
        card.prepend(error);
      }, { once: true });
      const caption = document.createElement('figcaption');
      const label = document.createElement('span');
      label.textContent = photo.caption || `Foto ${String(index + 1).padStart(2, '0')}`;
      const link = document.createElement('a');
      link.href = photo.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Open foto ↗';
      caption.append(label, link);
      card.append(img, caption);
      gallery.append(card);
    });
    document.querySelector('#photo-count').textContent = `${photos.length} ${photos.length === 1 ? 'foto' : 'foto’s'}`;
    results.hidden = false;
    showStatus(session.demo ? 'Dit zijn voorbeeldbeelden om de website te testen.' : 'Gevonden! Hieronder staan jouw foto’s.');
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    showStatus('Je foto’s konden niet worden opgehaald. Probeer opnieuw of vraag hulp bij de booth.', true);
  } finally {
    clearTimeout(timeout);
    button.disabled = false;
    input.disabled = false;
    form.removeAttribute('aria-busy');
  }
});

// A QR code may link directly to index.html?code=YOUR-CODE.
const ticketCode = new URLSearchParams(location.search).get('code');
if (ticketCode) {
  input.value = ticketCode.slice(0, 64);
  form.requestSubmit();
}
