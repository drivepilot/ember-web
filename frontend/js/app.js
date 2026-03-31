/**
 * Ember Web Dashboard - main application logic.
 */
(function () {
    const MODE_NAMES = { 0: 'Auto', 1: 'All Day', 2: 'On', 3: 'Off' };
    const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

    let zones = [];
    let ws = null;
    let pollInterval = null;

    // --- Init ---

    async function init() {
        try {
            const { logged_in } = await api.status();
            if (!logged_in) {
                window.location.href = '/login';
                return;
            }
        } catch {
            window.location.href = '/login';
            return;
        }

        await loadZones();
        connectWebSocket();
        startPolling();

        document.getElementById('refresh-btn').addEventListener('click', loadZones);
    }

    // --- Zone loading ---

    async function loadZones() {
        const loading = document.getElementById('loading');
        try {
            loading.hidden = false;
            zones = await api.getZones();
            renderZones(zones);
        } catch (err) {
            console.error('Failed to load zones:', err);
            loading.textContent = 'Failed to load zones. ' + err.message;
            loading.hidden = false;
        }
    }

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(loadZones, 30000); // refresh every 30s
    }

    // --- Rendering ---

    function renderZones(zones) {
        const dashboard = document.getElementById('dashboard');
        const loading = document.getElementById('loading');
        const template = document.getElementById('zone-template');

        // Clear existing cards but keep loading element
        dashboard.querySelectorAll('.zone-card').forEach(el => el.remove());
        loading.hidden = true;

        if (zones.length === 0) {
            loading.textContent = 'No zones found.';
            loading.hidden = false;
            return;
        }

        zones.forEach(zone => {
            const card = template.content.cloneNode(true);
            const el = card.querySelector('.zone-card');

            el.dataset.zone = zone.name;

            // Name and status
            el.querySelector('.zone-name').textContent = zone.name;
            const badge = el.querySelector('.zone-status-badge');
            if (zone.boiler_on) {
                badge.textContent = 'Heating';
                badge.classList.add('heating');
            } else if (zone.is_active) {
                badge.textContent = 'Active';
                badge.classList.add('active');
            } else {
                badge.textContent = 'Idle';
                badge.classList.add('idle');
            }

            // Temperatures
            el.querySelector('.current-temp').textContent = zone.current_temp.toFixed(1);
            el.querySelector('.target-temp').textContent = zone.target_temp.toFixed(1);

            // Temperature controls
            el.querySelector('.temp-down').addEventListener('click', () => {
                adjustTemp(zone.name, -0.5);
            });
            el.querySelector('.temp-up').addEventListener('click', () => {
                adjustTemp(zone.name, 0.5);
            });

            // Mode buttons
            el.querySelectorAll('.btn-mode').forEach(btn => {
                const mode = parseInt(btn.dataset.mode);
                if (mode === zone.mode) btn.classList.add('selected');
                btn.addEventListener('click', () => setMode(zone.name, mode));
            });

            // Boost buttons
            el.querySelector('.btn-boost').addEventListener('click', () => {
                activateBoost(zone.name, 1);
            });
            el.querySelector('[data-hours="2"]').addEventListener('click', () => {
                activateBoost(zone.name, 2);
            });

            const cancelBtn = el.querySelector('.btn-cancel-boost');
            cancelBtn.hidden = !zone.boost_active;
            cancelBtn.addEventListener('click', () => cancelBoost(zone.name));

            // Advance
            const advBtn = el.querySelector('.btn-advance');
            if (zone.advance_active) advBtn.classList.add('selected');
            advBtn.addEventListener('click', () => toggleAdvance(zone.name));

            // Schedule
            const scheduleBody = el.querySelector('.schedule-body');
            if (zone.schedule && zone.schedule.length > 0) {
                zone.schedule.forEach(day => {
                    const dayType = day.dayType ?? day.day_type;
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${DAY_NAMES[dayType] ?? dayType}</td>
                        <td>${formatTime(day.p1.startTime ?? day.p1.start_time)} - ${formatTime(day.p1.endTime ?? day.p1.end_time)}</td>
                        <td>${formatTime(day.p2.startTime ?? day.p2.start_time)} - ${formatTime(day.p2.endTime ?? day.p2.end_time)}</td>
                        <td>${formatTime(day.p3.startTime ?? day.p3.start_time)} - ${formatTime(day.p3.endTime ?? day.p3.end_time)}</td>
                    `;
                    scheduleBody.appendChild(row);
                });
            }

            el.querySelector('.toggle-schedule').addEventListener('click', function () {
                const sched = el.querySelector('.zone-schedule');
                sched.hidden = !sched.hidden;
                this.textContent = sched.hidden ? 'Show Schedule' : 'Hide Schedule';
            });

            dashboard.appendChild(el);
        });
    }

    function formatTime(t) {
        if (!t) return '--:--';
        const s = String(t);
        if (s.length < 2) return '--:--';
        const hours = s.slice(0, -1);
        const tenMins = s.slice(-1);
        return `${hours.padStart(2, '0')}:${tenMins}0`;
    }

    // --- Actions ---

    async function adjustTemp(zoneName, delta) {
        const zone = zones.find(z => z.name === zoneName);
        if (!zone) return;
        const newTemp = Math.max(5, Math.min(35, zone.target_temp + delta));
        try {
            await api.setTemperature(zoneName, newTemp);
            zone.target_temp = newTemp;
            updateTempDisplay(zoneName, newTemp);
        } catch (err) {
            alert('Failed to set temperature: ' + err.message);
        }
    }

    function updateTempDisplay(zoneName, temp) {
        const card = document.querySelector(`.zone-card[data-zone="${zoneName}"]`);
        if (card) {
            card.querySelector('.target-temp').textContent = temp.toFixed(1);
        }
    }

    async function setMode(zoneName, mode) {
        try {
            await api.setMode(zoneName, mode);
            const zone = zones.find(z => z.name === zoneName);
            if (zone) zone.mode = mode;
            const card = document.querySelector(`.zone-card[data-zone="${zoneName}"]`);
            if (card) {
                card.querySelectorAll('.btn-mode').forEach(btn => {
                    btn.classList.toggle('selected', parseInt(btn.dataset.mode) === mode);
                });
            }
        } catch (err) {
            alert('Failed to set mode: ' + err.message);
        }
    }

    async function activateBoost(zoneName, hours) {
        try {
            await api.activateBoost(zoneName, hours);
            await loadZones();
        } catch (err) {
            alert('Failed to activate boost: ' + err.message);
        }
    }

    async function cancelBoost(zoneName) {
        try {
            await api.cancelBoost(zoneName);
            await loadZones();
        } catch (err) {
            alert('Failed to cancel boost: ' + err.message);
        }
    }

    async function toggleAdvance(zoneName) {
        try {
            await api.toggleAdvance(zoneName);
            await loadZones();
        } catch (err) {
            alert('Failed to toggle advance: ' + err.message);
        }
    }

    // --- WebSocket ---

    function connectWebSocket() {
        const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${window.location.host}/ws/updates`;
        ws = new WebSocket(url);

        const dot = document.getElementById('connection-status');

        ws.onopen = () => {
            dot.classList.remove('disconnected');
            dot.classList.add('connected');
            dot.title = 'WebSocket connected';
        };

        ws.onclose = () => {
            dot.classList.remove('connected');
            dot.classList.add('disconnected');
            dot.title = 'WebSocket disconnected';
            // Reconnect after 5 seconds
            setTimeout(connectWebSocket, 5000);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleRealtimeUpdate(data);
            } catch {
                // ignore
            }
        };

        // Send periodic pings to keep connection alive
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
            }
        }, 25000);
    }

    function handleRealtimeUpdate(data) {
        // MQTT updates trigger a full zone refresh for simplicity
        loadZones();
    }

    // --- Start ---

    document.addEventListener('DOMContentLoaded', init);
})();
