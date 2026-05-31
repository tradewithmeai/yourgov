import * as THREE from 'https://cdn.jsdelivr.net/npm/three@0.164.1/build/three.module.js';
import { feature as topoFeature } from 'https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/+esm';

const BORDERS_URL = 'https://cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-110m.json';

const STATUS_COLOURS = {
  green: '#16a34a',
  orange: '#f59e0b',
  red: '#dc2626',
};

const STATUS_TEXT = {
  green: 'Strong candidate',
  orange: 'Possible with work',
  red: 'Insufficient verified data',
};

const LIVE_LABEL = 'Completed and live';
const LIVE_COLOUR = '#39ff14';

const shell = document.querySelector('.global-shell');
const stage = document.getElementById('globe-stage');
const loading = document.getElementById('globe-loading');
const tooltip = document.getElementById('global-tooltip');
const countrySearchWrap = document.getElementById('country-search-wrap');
const countrySearchInput = document.getElementById('country-search-input');
const countrySearchResults = document.getElementById('country-search-results');
const legendFilters = Array.from(document.querySelectorAll('.legend-filter'));
const countryListCard = document.getElementById('country-list-card');
const countryCard = document.getElementById('country-card');
const filterTitle = document.getElementById('filter-title');
const filterMeta = document.getElementById('filter-meta');
const filterList = document.getElementById('filter-list');
const filterBack = document.getElementById('filter-back');
const entryModal = document.getElementById('entry-modal');
const entryModalTitle = document.getElementById('entry-modal-title');
const entryModalCopy = document.getElementById('entry-modal-copy');
const entryModalLiveNote = document.getElementById('entry-modal-live-note');
const entryModalLiveCountry = document.getElementById('entry-modal-live-country');
const entryOpenSite = document.getElementById('entry-open-site');
const entryChooseCountry = document.getElementById('entry-choose-country');

const els = {
  live: document.getElementById('stat-live'),
  green: document.getElementById('stat-green'),
  orange: document.getElementById('stat-orange'),
  red: document.getElementById('stat-red'),
  unmapped: document.getElementById('stat-unmapped'),
  countryName: document.getElementById('country-name'),
  countryStatus: document.getElementById('country-status'),
  statusDot: document.getElementById('status-dot'),
  countrySummary: document.getElementById('country-summary'),
  countryTier: document.getElementById('country-tier'),
  countryConfidence: document.getElementById('country-confidence'),
  countryScore: document.getElementById('country-score'),
  availableData: document.getElementById('available-data'),
  missingData: document.getElementById('missing-data'),
  nextAction: document.getElementById('next-action'),
};

const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const dataUrl = shell?.dataset.feasibilityUrl || '/api/global/feasibility';
const activeLocale = shell?.dataset.locale || 'en';
const pageParams = new URLSearchParams(window.location.search);
const EARTH_AXIAL_TILT_RAD = THREE.MathUtils.degToRad(-23.44);

function toLensUrl(country) {
  const cc = encodeURIComponent(((country && country.iso2) || 'GB').toUpperCase());
  const lang = encodeURIComponent(activeLocale || 'en');
  return `/source-lens?source=lens&cc=${cc}&lang=${lang}`;
}

function maybeShowEntryModal(country) {
  if (!entryModal || !country) return;
  if (pageParams.get('from') !== 'start') return;

  const isLive = !!country.working_adapter;
  entryModal.hidden = false;
  entryModal.setAttribute('aria-hidden', 'false');
  if (entryModalLiveCountry) entryModalLiveCountry.textContent = country.name || 'your country';

  if (isLive) {
    if (entryModalTitle) entryModalTitle.textContent = `Enter ${country.name || 'your'} MyGov site?`;
    if (entryModalCopy) entryModalCopy.textContent = 'A live adapter is available for your country. Enter now or keep exploring the globe first.';
    if (entryModalLiveNote) entryModalLiveNote.hidden = false;
    if (entryOpenSite) {
      entryOpenSite.hidden = false;
      entryOpenSite.textContent = 'Enter your site';
      entryOpenSite.onclick = () => { window.location.href = toLensUrl(country); };
    }
  } else {
    if (entryModalTitle) entryModalTitle.textContent = `Explore ${country.name || 'your country'} readiness`;
    if (entryModalCopy) entryModalCopy.textContent = 'Your country does not have a live adapter yet. Explore feasibility and pick any country on the globe.';
    if (entryModalLiveNote) entryModalLiveNote.hidden = true;
    if (entryOpenSite) {
      entryOpenSite.hidden = true;
      entryOpenSite.onclick = null;
    }
  }

  if (entryChooseCountry) {
    entryChooseCountry.onclick = () => {
      entryModal.hidden = true;
      entryModal.setAttribute('aria-hidden', 'true');
      countrySearchInput?.focus();
    };
  }
}

let scene;
let camera;
let renderer;
let globeGroup;
let axialGroup;
let spinGroup;
let markerGroup;
let raycaster;
let pointer;
let markers = [];
let selectedMarker = null;
let hoveredMarker = null;
let dragging = false;
let lastPointer = { x: 0, y: 0 };
let animationFrame = null;
let countriesData = [];
let searchMatches = [];
let focusedSearchIndex = -1;
let focusQuaternion = null;
let focusAnimating = false;
let activeFilter = null;

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatKey(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatValue(value) {
  return String(value ?? 'unknown').replace(/_/g, ' ');
}

function updateStats(payload) {
  const counts = payload.counts || payload.countries.reduce((acc, country) => {
    acc[country.status] = (acc[country.status] || 0) + 1;
    if (country.working_adapter) {
      acc.live += 1;
    }
    acc.total += 1;
    return acc;
  }, { live: 0, green: 0, orange: 0, red: 0, total: 0 });

  const liveCount = counts.live ?? payload.countries.filter((country) => country.working_adapter).length;
  const unmappedCount = counts.red ?? payload.countries.filter((country) => country.status === 'red').length;
  els.live.textContent = liveCount;
  els.green.textContent = counts.green ?? 0;
  els.orange.textContent = counts.orange ?? 0;
  els.red.textContent = counts.red ?? 0;
  els.unmapped.textContent = unmappedCount;
}

function getCountryStatusLabel(country) {
  if (country?.working_adapter) return LIVE_LABEL;
  return country?.status_label || STATUS_TEXT[country?.status] || country?.status || 'Unknown';
}

function setStatusDot(status, isLive = false) {
  els.statusDot.className = `status-dot ${isLive ? 'live' : status}`;
}

function fillList(node, items, mode = 'plain') {
  node.innerHTML = '';
  items.forEach((item) => {
    const li = document.createElement('li');
    li.textContent = item;
    if (mode === 'chips') {
      li.title = item;
    }
    node.appendChild(li);
  });
}

function selectCountry(country, marker = null) {
  if (!country) return;

  if (selectedMarker && selectedMarker !== marker) {
    selectedMarker.userData.selected = false;
  }
  selectedMarker = marker || markers.find((candidate) => candidate.userData.country.iso2 === country.iso2) || null;
  if (selectedMarker) {
    selectedMarker.userData.selected = true;
  }

  els.countryName.textContent = country.name;
  els.countryStatus.textContent = getCountryStatusLabel(country);
  els.countrySummary.textContent = country.summary || 'No summary is available for this country.';
  els.countryTier.textContent = country.tier || 'Not assessed';
  els.countryConfidence.textContent = country.confidence || 'unknown';
  els.countryScore.textContent = country.score == null ? 'not scored in extract' : String(country.score);
  els.nextAction.textContent = country.next_action || 'Run a source audit before adapter work.';
  setStatusDot(country.status, !!country.working_adapter);
  const available = Object.entries(country.available_data || {}).map(([key, value]) => `${formatKey(key)}: ${formatValue(value)}`);
  fillList(els.availableData, available, 'chips');
  fillList(els.missingData, country.missing_data || ['Country-specific source review required.']);
}

function latLonToVector3(lat, lon, radius) {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function createPlusTexture(colour, isWorkingAdapter = false) {
  const size = 128;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  const centre = size / 2;

  ctx.clearRect(0, 0, size, size);
  const glow = ctx.createRadialGradient(centre, centre, 5, centre, centre, 58);
  glow.addColorStop(0, colour);
  glow.addColorStop(0.28, `${colour}cc`);
  glow.addColorStop(1, `${colour}00`);
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(centre, centre, 58, 0, Math.PI * 2);
  ctx.fill();

  if (isWorkingAdapter) {
    const spikes = 5;
    const outerRadius = 40;
    const innerRadius = 18;
    let rot = (Math.PI / 2) * 3;
    const step = Math.PI / spikes;
    ctx.beginPath();
    ctx.moveTo(centre, centre - outerRadius);
    for (let i = 0; i < spikes; i += 1) {
      ctx.lineTo(centre + Math.cos(rot) * outerRadius, centre + Math.sin(rot) * outerRadius);
      rot += step;
      ctx.lineTo(centre + Math.cos(rot) * innerRadius, centre + Math.sin(rot) * innerRadius);
      rot += step;
    }
    ctx.lineTo(centre, centre - outerRadius);
    ctx.closePath();
    ctx.fillStyle = LIVE_COLOUR;
    ctx.shadowColor = LIVE_COLOUR;
    ctx.shadowBlur = 20;
    ctx.fill();
    ctx.shadowBlur = 0;
    ctx.strokeStyle = 'rgba(255,255,255,0.95)';
    ctx.lineWidth = 3;
    ctx.stroke();
  } else {
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = colour;
    ctx.shadowColor = colour;
    ctx.shadowBlur = 20;
    ctx.lineWidth = 11;
    ctx.beginPath();
    ctx.moveTo(centre, 31);
    ctx.lineTo(centre, 97);
    ctx.moveTo(31, centre);
    ctx.lineTo(97, centre);
    ctx.stroke();

    ctx.shadowBlur = 0;
    ctx.strokeStyle = 'rgba(255,255,255,0.92)';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(centre, 38);
    ctx.lineTo(centre, 90);
    ctx.moveTo(38, centre);
    ctx.lineTo(90, centre);
    ctx.stroke();
  }

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function createMarker(country, radius) {
  const colour = STATUS_COLOURS[country.status] || STATUS_COLOURS.red;
  const material = new THREE.SpriteMaterial({
    map: createPlusTexture(colour, country.working_adapter),
    transparent: true,
    depthTest: true,
    depthWrite: false,
  });
  const sprite = new THREE.Sprite(material);
  const position = latLonToVector3(country.lat, country.lon, radius);
  sprite.position.copy(position);
  const baseSize = country.working_adapter ? 0.27 : country.status === 'green' ? 0.22 : 0.19;
  sprite.scale.set(baseSize, baseSize, 1);
  sprite.userData = {
    country,
    baseSize,
    selected: false,
    phase: Math.random() * Math.PI * 2,
  };
  return sprite;
}

function focusCountryOnGlobe(country) {
  if (!country || !globeGroup) return;
  const from = latLonToVector3(country.lat, country.lon, 1).normalize();
  const to = new THREE.Vector3(0, 0, 1);
  focusQuaternion = new THREE.Quaternion().setFromUnitVectors(from, to);
  focusAnimating = true;
}

function createStars() {
  const count = 700;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const radius = 9 + Math.random() * 12;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.cos(phi);
    positions[i * 3 + 2] = radius * Math.sin(phi) * Math.sin(theta);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  const material = new THREE.PointsMaterial({
    color: '#94a3b8',
    size: 0.018,
    transparent: true,
    opacity: 0.48,
  });
  return new THREE.Points(geometry, material);
}

function createGlobe(countries) {
  scene = new THREE.Scene();
  scene.fog = new THREE.Fog('#020617', 7, 22);

  camera = new THREE.PerspectiveCamera(46, stage.clientWidth / stage.clientHeight, 0.1, 100);
  // Wider default framing so the full globe is clearly visible on first paint.
  camera.position.set(0, 0, 7.25);

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setSize(stage.clientWidth, stage.clientHeight);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  stage.appendChild(renderer.domElement);

  raycaster = new THREE.Raycaster();
  pointer = new THREE.Vector2();

  scene.add(createStars());

  const ambient = new THREE.AmbientLight('#dbeafe', 0.95);
  scene.add(ambient);
  const key = new THREE.DirectionalLight('#ffffff', 1.45);
  key.position.set(4, 3, 5);
  scene.add(key);
  const rim = new THREE.DirectionalLight('#38bdf8', 0.9);
  rim.position.set(-4, -2, -3);
  scene.add(rim);

  // Nested transform: outer globeGroup carries the user-orbit + the
  // fixed axial tilt (Earth's ~23.5° obliquity, applied around Z so
  // the pole leans to the user's right). Inner spinGroup carries the
  // earth, borders, markers — and is the ONLY thing rotated by the
  // idle auto-spin, so the spin happens around the tilted pole and
  // continents no longer precess against a vertical world-Y axis.
  globeGroup = new THREE.Group();
  globeGroup.rotation.y = -0.54;            // initial framing yaw
  // ~23.5° axial tilt. Negative Z rotation leans the north pole to
  // the LEFT (west) in the image — matching Earth-style obliquity as
  // commonly drawn with the pole offset toward the camera's left.
  // (The composition with the existing -0.54 yaw flips the visible
  // direction vs. a bare Z rotation, so the sign here is the one
  // verified by eye to give west-lean.)
  scene.add(globeGroup);

  axialGroup = new THREE.Group();
  axialGroup.rotation.z = EARTH_AXIAL_TILT_RAD;
  globeGroup.add(axialGroup);

  spinGroup = new THREE.Group();
  axialGroup.add(spinGroup);

  const earthRadius = 2.2;
  const earth = new THREE.Mesh(
    new THREE.SphereGeometry(earthRadius, 96, 64),
    new THREE.MeshPhongMaterial({
      color: '#0f2a3d',
      emissive: '#06111f',
      emissiveIntensity: 0.54,
      specular: '#7dd3fc',
      shininess: 26,
    }),
  );
  spinGroup.add(earth);

  const wire = new THREE.Mesh(
    new THREE.SphereGeometry(earthRadius + 0.006, 48, 24),
    new THREE.MeshBasicMaterial({
      color: '#38bdf8',
      wireframe: true,
      transparent: true,
      opacity: 0.075,
    }),
  );
  spinGroup.add(wire);

  const atmosphere = new THREE.Mesh(
    new THREE.SphereGeometry(earthRadius + 0.12, 96, 64),
    new THREE.MeshBasicMaterial({
      color: '#38bdf8',
      transparent: true,
      opacity: 0.09,
      side: THREE.BackSide,
    }),
  );
  spinGroup.add(atmosphere);

  markerGroup = new THREE.Group();
  markers = countries.map((country) => createMarker(country, earthRadius + 0.16));
  markers.forEach((marker) => markerGroup.add(marker));
  spinGroup.add(markerGroup);

  addCountryBorders(earthRadius + 0.012);

  bindControls();
  animate();
}

function buildBorderSegments(geojson, radius) {
  const positions = [];

  const pushRing = (ring) => {
    if (!ring || ring.length < 2) return;
    for (let i = 0; i < ring.length - 1; i += 1) {
      const [lon1, lat1] = ring[i];
      const [lon2, lat2] = ring[i + 1];
      const a = latLonToVector3(lat1, lon1, radius);
      const b = latLonToVector3(lat2, lon2, radius);
      positions.push(a.x, a.y, a.z, b.x, b.y, b.z);
    }
  };

  const pushPolygon = (polygon) => polygon.forEach(pushRing);

  geojson.features.forEach((feat) => {
    const geom = feat.geometry;
    if (!geom) return;
    if (geom.type === 'Polygon') {
      pushPolygon(geom.coordinates);
    } else if (geom.type === 'MultiPolygon') {
      geom.coordinates.forEach(pushPolygon);
    }
  });

  return new Float32Array(positions);
}

function addCountryBorders(radius) {
  fetch(BORDERS_URL, { headers: { Accept: 'application/json' } })
    .then((response) => {
      if (!response.ok) throw new Error(`Borders request failed: ${response.status}`);
      return response.json();
    })
    .then((topo) => {
      const collection = topoFeature(topo, topo.objects.countries);
      const positions = buildBorderSegments(collection, radius);
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      const material = new THREE.LineBasicMaterial({
        color: '#7dd3fc',
        transparent: true,
        opacity: 0.55,
      });
      const borders = new THREE.LineSegments(geometry, material);
      borders.renderOrder = 1;
      // Borders share the rest of the earth's rotation, so attach to
      // spinGroup (not globeGroup) — keeps continents locked to the
      // tilted spin axis instead of precessing around world-Y.
      spinGroup.add(borders);
    })
    .catch((error) => {
      // eslint-disable-next-line no-console
      console.warn('Country borders unavailable:', error);
    });
}

function normalisePointer(event) {
  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
}

function intersectMarker(event) {
  if (!renderer || !camera) return null;
  normalisePointer(event);
  raycaster.setFromCamera(pointer, camera);
  const hits = raycaster.intersectObjects(markers, false);
  return hits.length ? hits[0].object : null;
}

function showTooltip(event, marker) {
  const country = marker.userData.country;
  tooltip.innerHTML = `<strong>${escapeHtml(country.name)}</strong>${escapeHtml(country.status_label || STATUS_TEXT[country.status])}`;
  const rect = stage.getBoundingClientRect();
  tooltip.style.left = `${event.clientX - rect.left + 14}px`;
  tooltip.style.top = `${event.clientY - rect.top + 14}px`;
  tooltip.hidden = false;
}

function hideTooltip() {
  tooltip.hidden = true;
  hoveredMarker = null;
}

function bindControls() {
  stage.addEventListener('pointerdown', (event) => {
    dragging = true;
    focusAnimating = false;
    lastPointer = { x: event.clientX, y: event.clientY };
    stage.setPointerCapture(event.pointerId);
  });

  stage.addEventListener('pointerup', (event) => {
    dragging = false;
    try { stage.releasePointerCapture(event.pointerId); } catch (_err) { /* pointer may already be released */ }
  });

  stage.addEventListener('pointerleave', () => {
    dragging = false;
    hideTooltip();
  });

  stage.addEventListener('pointermove', (event) => {
    if (dragging) {
      const dx = event.clientX - lastPointer.x;
      const dy = event.clientY - lastPointer.y;
      globeGroup.rotation.y += dx * 0.005;
      globeGroup.rotation.x += dy * 0.0035;
      globeGroup.rotation.x = THREE.MathUtils.clamp(globeGroup.rotation.x, -1.15, 1.15);
      lastPointer = { x: event.clientX, y: event.clientY };
      hideTooltip();
      return;
    }

    const hit = intersectMarker(event);
    hoveredMarker = hit;
    if (hit) {
      showTooltip(event, hit);
      stage.style.cursor = 'pointer';
    } else {
      hideTooltip();
      stage.style.cursor = 'grab';
    }
  });

  stage.addEventListener('click', (event) => {
    if (!renderer) return;
    const hit = intersectMarker(event);
    if (hit) {
      const country = hit.userData.country;
      selectCountry(country, hit);
      if (country && country.working_adapter) {
        window.location.href = toLensUrl(country);
      }
    }
  });

  stage.addEventListener('wheel', (event) => {
    event.preventDefault();
    const nextZ = camera.position.z + event.deltaY * 0.003;
    camera.position.z = THREE.MathUtils.clamp(nextZ, 5.4, 10.2);
  }, { passive: false });

  stage.addEventListener('keydown', (event) => {
    const step = 0.12;
    if (event.key === 'ArrowLeft') globeGroup.rotation.y -= step;
    if (event.key === 'ArrowRight') globeGroup.rotation.y += step;
    if (event.key === 'ArrowUp') globeGroup.rotation.x = THREE.MathUtils.clamp(globeGroup.rotation.x - step, -1.15, 1.15);
    if (event.key === 'ArrowDown') globeGroup.rotation.x = THREE.MathUtils.clamp(globeGroup.rotation.x + step, -1.15, 1.15);
  });

  window.addEventListener('resize', resizeGlobe);
}

function getSearchMatches(query) {
  const q = (query || '').trim().toLowerCase();
  if (q.length < 1) return [];
  const starts = [];
  const contains = [];
  countriesData.forEach((country) => {
    const name = (country.name || '').toLowerCase();
    if (!name) return;
    if (name.startsWith(q)) starts.push(country);
    else if (name.includes(q)) contains.push(country);
  });
  return starts.concat(contains).slice(0, 8);
}

function renderSearchMatches() {
  if (!countrySearchResults) return;
  countrySearchResults.innerHTML = '';
  if (!searchMatches.length) {
    countrySearchResults.hidden = true;
    return;
  }

  const frag = document.createDocumentFragment();
  searchMatches.forEach((country, index) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'country-search-item';
    if (index === focusedSearchIndex) btn.classList.add('active');
    btn.setAttribute('data-index', String(index));
    btn.setAttribute('data-iso2', country.iso2 || '');
    btn.innerHTML = `<span>${escapeHtml(country.name)}</span><span class="country-search-meta">${escapeHtml(country.status_label || STATUS_TEXT[country.status] || '')}</span>`;
    frag.appendChild(btn);
  });
  countrySearchResults.appendChild(frag);
  countrySearchResults.hidden = false;
}

function applyCountrySelection(country) {
  if (!country) return;
  countrySearchInput.value = country.name || '';
  searchMatches = [];
  focusedSearchIndex = -1;
  renderSearchMatches();
  const marker = markers.find((m) => m.userData.country.iso2 === country.iso2);
  selectCountry(country, marker || null);
  focusCountryOnGlobe(country);
  clearCountryFilterView();
}

function previewTopCountry(country) {
  if (!country) return;
  const marker = markers.find((m) => m.userData.country.iso2 === country.iso2);
  selectCountry(country, marker || null);
  focusCountryOnGlobe(country);
}

function getCountriesForFilter(filterKey) {
  if (filterKey === 'live') return countriesData.filter((country) => !!country.working_adapter);
  if (filterKey === 'green') return countriesData.filter((country) => country.status === 'green' && !country.working_adapter);
  if (filterKey === 'orange') return countriesData.filter((country) => country.status === 'orange');
  if (filterKey === 'red') return countriesData.filter((country) => country.status === 'red');
  return [];
}

function getFilterTitle(filterKey) {
  if (filterKey === 'live') return 'Completed & live adapters';
  if (filterKey === 'green') return 'Strong candidates';
  if (filterKey === 'orange') return 'Possible with work';
  if (filterKey === 'red') return 'Not build-ready';
  return 'Countries';
}

function renderCountryFilterView(filterKey) {
  const items = getCountriesForFilter(filterKey).sort((a, b) => (a.name || '').localeCompare(b.name || ''));
  activeFilter = filterKey;
  legendFilters.forEach((btn) => btn.classList.toggle('active', btn.dataset.filter === filterKey));
  if (!countryListCard || !countryCard || !filterTitle || !filterMeta || !filterList) return;

  filterTitle.textContent = getFilterTitle(filterKey);
  filterMeta.textContent = `${items.length} countries`;
  filterList.innerHTML = '';
  items.forEach((country) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'country-filter-item';
    btn.innerHTML = `<span>${escapeHtml(country.name)}</span><span class="country-search-meta">${escapeHtml(getCountryStatusLabel(country))}</span>`;
    btn.addEventListener('click', () => {
      const marker = markers.find((m) => m.userData.country.iso2 === country.iso2) || null;
      selectCountry(country, marker);
      focusCountryOnGlobe(country);
      clearCountryFilterView();
    });
    filterList.appendChild(btn);
  });

  countryCard.hidden = true;
  countryListCard.hidden = false;
}

function clearCountryFilterView() {
  activeFilter = null;
  legendFilters.forEach((btn) => btn.classList.remove('active'));
  if (!countryListCard || !countryCard) return;
  countryListCard.hidden = true;
  countryCard.hidden = false;
}

function bindCountrySearch() {
  if (!countrySearchInput || !countrySearchResults) return;

  countrySearchInput.addEventListener('input', () => {
    searchMatches = getSearchMatches(countrySearchInput.value);
    focusedSearchIndex = searchMatches.length ? 0 : -1;
    renderSearchMatches();
    if (searchMatches.length) {
      previewTopCountry(searchMatches[0]);
    }
  });

  countrySearchInput.addEventListener('keydown', (event) => {
    if (!searchMatches.length) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      focusedSearchIndex = Math.min(focusedSearchIndex + 1, searchMatches.length - 1);
      renderSearchMatches();
      previewTopCountry(searchMatches[focusedSearchIndex]);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      focusedSearchIndex = Math.max(focusedSearchIndex - 1, 0);
      renderSearchMatches();
      previewTopCountry(searchMatches[focusedSearchIndex]);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      const pick = searchMatches[focusedSearchIndex >= 0 ? focusedSearchIndex : 0];
      applyCountrySelection(pick);
      return;
    }
    if (event.key === 'Escape') {
      searchMatches = [];
      focusedSearchIndex = -1;
      renderSearchMatches();
    }
  });

  countrySearchResults.addEventListener('click', (event) => {
    const btn = event.target.closest('.country-search-item');
    if (!btn) return;
    const index = Number(btn.getAttribute('data-index'));
    const pick = searchMatches[index];
    if (pick) applyCountrySelection(pick);
  });

  document.addEventListener('click', (event) => {
    if (!countrySearchWrap || !countrySearchWrap.contains(event.target)) {
      searchMatches = [];
      focusedSearchIndex = -1;
      renderSearchMatches();
    }
  });
}

function bindLegendFilters() {
  if (!legendFilters.length) return;
  legendFilters.forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.filter;
      if (!key) return;
      if (activeFilter === key) {
        clearCountryFilterView();
      } else {
        renderCountryFilterView(key);
      }
    });
  });
  if (filterBack) {
    filterBack.addEventListener('click', clearCountryFilterView);
  }
}

function resizeGlobe() {
  if (!renderer || !camera) return;
  const width = stage.clientWidth;
  const height = stage.clientHeight;
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
  renderer.setSize(width, height);
}

function animate(time = 0) {
  animationFrame = window.requestAnimationFrame(animate);

  if (focusAnimating && focusQuaternion && !dragging) {
    globeGroup.quaternion.slerp(focusQuaternion, reducedMotion ? 1 : 0.1);
    if (globeGroup.quaternion.angleTo(focusQuaternion) < 0.0025) {
      globeGroup.quaternion.copy(focusQuaternion);
      focusAnimating = false;
    }
  }

  if (!reducedMotion && !dragging && !focusAnimating) {
    // Idle spin around the tilted pole. At 60fps and 2π per rotation,
    // 0.0017 rad/frame ≈ 0.102 rad/s ≈ 61.6s per full rotation —
    // stately, demo-friendly, hints at planetary motion. Rotates the
    // inner spinGroup so the tilt stays fixed in world space.
    spinGroup.rotation.y += 0.0017;
  }

  markers.forEach((marker) => {
    const { baseSize, selected, phase } = marker.userData;
    const hover = marker === hoveredMarker ? 1.2 : 1;
    const selectedBoost = selected ? 1.32 : 1;
    const pulseStrength = marker.userData.country?.working_adapter ? 0.14 : 0.055;
    const pulse = reducedMotion ? 1 : 1 + Math.sin(time * 0.002 + phase) * pulseStrength;
    const scale = baseSize * hover * selectedBoost * pulse;
    marker.scale.set(scale, scale, 1);
    marker.material.opacity = selected ? 1 : marker === hoveredMarker ? 0.98 : 0.86;
  });

  renderer.render(scene, camera);
}

async function loadData() {
  const response = await fetch(dataUrl, { headers: { Accept: 'application/json' } });
  if (!response.ok) {
    throw new Error(`Feasibility data request failed: ${response.status}`);
  }
  const payload = await response.json();
  if (!payload || !Array.isArray(payload.countries) || payload.countries.length === 0) {
    throw new Error('Feasibility data contains no countries.');
  }
  return payload;
}

function resolveInitialCountry(countries) {
  // Precedence: URL ?cc= override → data-active-cc on the shell
  // (server-resolved from geo headers) → GB → first country.
  const urlCc = (new URLSearchParams(window.location.search).get('cc') || '').toUpperCase();
  const dataCc = (shell?.dataset.activeCc || '').toUpperCase();
  const tryCodes = [urlCc, dataCc, 'GB'].filter(Boolean);
  for (const code of tryCodes) {
    const match = countries.find((c) => (c.iso2 || '').toUpperCase() === code);
    if (match) return match;
  }
  return countries[0];
}

function start() {
  loadData()
    .then((payload) => {
      countriesData = payload.countries || [];
      updateStats(payload);
      createGlobe(payload.countries);
      const initial = resolveInitialCountry(payload.countries);
      selectCountry(initial);
      if (initial) focusCountryOnGlobe(initial);
      if (countrySearchInput && initial) countrySearchInput.value = initial.name || '';
      maybeShowEntryModal(initial);
      bindCountrySearch();
      bindLegendFilters();
      loading.hidden = true;
    })
    .catch((error) => {
      loading.textContent = `Could not load globe data: ${error.message}`;
      loading.classList.add('error');
      // eslint-disable-next-line no-console
      console.error(error);
    });
}

start();

window.addEventListener('beforeunload', () => {
  if (animationFrame) window.cancelAnimationFrame(animationFrame);
});
