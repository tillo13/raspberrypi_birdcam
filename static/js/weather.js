// Ambient conditions from the Sense HAT. Wrapped in an IIFE because birds.js and
// motion.js both live at top-level scope and already claim names like `status`.
(function () {
  const REFRESH_MS = 60000;

  const bar = document.getElementById('conditions');
  const elTemp = document.getElementById('condTemp');
  const elHumidity = document.getElementById('condHumidity');
  const elPressure = document.getElementById('condPressure');
  const elNote = document.getElementById('condNote');
  const sayBtn = document.getElementById('condSay');

  let latest = null;

  async function refresh() {
    try {
      const res = await fetch('/api/weather');
      const data = await res.json();
      if (!data.success) { bar.hidden = true; return; }

      latest = data;
      elTemp.textContent = `${data.temp_c.toFixed(1)}°C`;
      elHumidity.textContent = `${data.humidity.toFixed(0)}%`;
      elPressure.textContent = `${data.pressure.toFixed(0)} hPa`;
      // The board sits in the Pi's exhaust, so show the working, not just the answer.
      elNote.title =
        `Sensor read ${data.raw_temp_c}°C / ${data.raw_humidity}% RH with the CPU at ` +
        `${data.cpu_temp_c}°C. Corrected toward ambient by subtracting a share of that ` +
        `gap — an estimate, not a calibrated thermometer.`;
      bar.hidden = false;
    } catch (err) {
      console.error('weather:', err);
      bar.hidden = true;
    }
  }

  sayBtn.addEventListener('click', async () => {
    if (!latest) return;
    sayBtn.disabled = true;
    sayBtn.textContent = 'Scrolling…';
    try {
      await fetch('/api/say', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `${Math.round(latest.temp_c)}C ${Math.round(latest.humidity)}%`
        })
      });
    } catch (err) {
      console.error('say:', err);
    }
    // Long enough for the matrix to finish the scroll before it can be retriggered.
    setTimeout(() => { sayBtn.disabled = false; sayBtn.textContent = 'Say it →'; }, 6000);
  });

  refresh();
  setInterval(refresh, REFRESH_MS);
})();
