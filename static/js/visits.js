// Bird visits: motion captures clustered into events, plus an activity histogram
// and the day's timelapse. IIFE-scoped — birds.js/motion.js own the global scope.
(function () {
  const REFRESH_MS = 30000;
  const POLL_MS = 3000;

  const listEl = document.getElementById('visitList');
  const stripEl = document.getElementById('activityStrip');
  const peakEl = document.getElementById('activityPeak');
  const summaryEl = document.getElementById('visitsSummary');
  const timelapseBtn = document.getElementById('timelapseBtn');

  const HOUR_LABEL = h => `${((h + 11) % 12) + 1}${h < 12 ? 'a' : 'p'}`;

  function renderStrip(hours) {
    const peak = Math.max(...hours);
    stripEl.innerHTML = hours.map((n, h) => {
      const height = peak ? Math.max(3, Math.round((n / peak) * 100)) : 3;
      const cls = n === 0 ? '' : (n === peak ? ' has-motion peak' : ' has-motion');
      return `<div class="activity-bar${cls}" style="height:${height}%" ` +
             `title="${HOUR_LABEL(h)} — ${n} trigger${n === 1 ? '' : 's'}"></div>`;
    }).join('');

    const total = hours.reduce((a, b) => a + b, 0);
    peakEl.textContent = peak
      ? `${total} triggers · busiest ${HOUR_LABEL(hours.indexOf(peak))}`
      : 'no motion yet today';
  }

  function timeRange(visit) {
    const start = new Date(visit.start);
    const clock = start.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    const date = start.toLocaleDateString([], { month: 'short', day: 'numeric' });
    return `${date} · ${clock}`;
  }

  function duration(seconds) {
    if (seconds < 60) return `${seconds}s`;
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
  }

  function renderVisits(visits) {
    if (!visits.length) {
      listEl.innerHTML = '<div class="empty">No bird visits yet. Turn on Motion Mode and wait.</div>';
      summaryEl.textContent = '';
      return;
    }
    summaryEl.textContent = `${visits.length} recent`;
    listEl.innerHTML = visits.map(v => {
      const tags = [`<span class="visit-tag">${v.triggers} trigger${v.triggers === 1 ? '' : 's'}</span>`];
      if (v.duration_s > 0) tags.push(`<span class="visit-tag">${duration(v.duration_s)}</span>`);
      if (v.temp_c !== null) {
        tags.push(`<span class="visit-tag weather">${v.temp_c.toFixed(1)}°C · ${v.humidity.toFixed(0)}%</span>`);
      }
      const links = [];
      if (v.thumbnail) links.push(`<a href="/files/${v.thumbnail}" target="_blank">Photo</a>`);
      if (v.clip) links.push(`<a href="/files/${v.clip}" target="_blank">Clip</a>`);
      const thumb = v.thumbnail
        ? `<img class="visit-thumb" src="/files/${v.thumbnail}" alt="" loading="lazy">`
        : '<div class="visit-thumb"></div>';
      return `
        <div class="visit-item">
          ${thumb}
          <div class="visit-body">
            <div class="visit-when">${timeRange(v)}</div>
            <div class="visit-meta">${tags.join('')}</div>
          </div>
          <div class="visit-links">${links.join('')}</div>
        </div>`;
    }).join('');
  }

  async function refresh() {
    try {
      const res = await fetch('/api/visits');
      const data = await res.json();
      if (!data.success) return;
      renderStrip(data.hours);
      renderVisits(data.visits);
    } catch (err) {
      console.error('visits:', err);
      listEl.innerHTML = '<div class="error">Failed to load visits</div>';
    }
  }

  async function pollTimelapse() {
    try {
      const res = await fetch('/api/timelapse_status');
      const data = await res.json();
      if (data.state === 'running') {
        timelapseBtn.innerHTML = `<span>⏳</span><span>${data.message}</span>`;
        setTimeout(pollTimelapse, POLL_MS);
        return;
      }
      if (data.state === 'done') {
        timelapseBtn.innerHTML = '<span>✅</span><span>Timelapse ready</span>';
        window.open(`/files/${data.filename}`, '_blank');
      } else if (data.state === 'error') {
        timelapseBtn.innerHTML = '<span>⚠️</span><span>Timelapse failed</span>';
        console.error('timelapse:', data.message);
      }
    } catch (err) {
      console.error('timelapse status:', err);
    }
    setTimeout(() => {
      timelapseBtn.innerHTML = '<span>🎬</span><span>Timelapse</span>';
      timelapseBtn.disabled = false;
    }, 4000);
  }

  timelapseBtn.addEventListener('click', async () => {
    timelapseBtn.disabled = true;
    timelapseBtn.innerHTML = '<span>⏳</span><span>Starting…</span>';
    try {
      const res = await fetch('/api/timelapse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const data = await res.json();
      if (!data.success) {
        timelapseBtn.innerHTML = `<span>⚠️</span><span>${data.message}</span>`;
        setTimeout(() => {
          timelapseBtn.innerHTML = '<span>🎬</span><span>Timelapse</span>';
          timelapseBtn.disabled = false;
        }, 4000);
        return;
      }
      pollTimelapse();
    } catch (err) {
      console.error('timelapse:', err);
      timelapseBtn.disabled = false;
      timelapseBtn.innerHTML = '<span>🎬</span><span>Timelapse</span>';
    }
  });

  refresh();
  setInterval(refresh, REFRESH_MS);
})();
