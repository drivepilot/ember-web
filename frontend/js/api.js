/**
 * API client for the Ember Web backend.
 */
const api = {
    async _fetch(url, options = {}) {
        const resp = await fetch(url, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (resp.status === 401) {
            window.location.href = '/login';
            throw new Error('Not logged in');
        }
        if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.detail || `Request failed (${resp.status})`);
        }
        return resp.json();
    },

    login(username, password) {
        return this._fetch('/api/login', {
            method: 'POST',
            body: JSON.stringify({ username, password }),
        });
    },

    status() {
        return this._fetch('/api/status');
    },

    getZones() {
        return this._fetch('/api/zones');
    },

    setTemperature(zoneName, temperature) {
        return this._fetch(`/api/zones/${encodeURIComponent(zoneName)}/temperature`, {
            method: 'POST',
            body: JSON.stringify({ temperature }),
        });
    },

    setMode(zoneName, mode) {
        return this._fetch(`/api/zones/${encodeURIComponent(zoneName)}/mode`, {
            method: 'POST',
            body: JSON.stringify({ mode }),
        });
    },

    activateBoost(zoneName, hours = 1, temperature = null) {
        const body = { hours };
        if (temperature !== null) body.temperature = temperature;
        return this._fetch(`/api/zones/${encodeURIComponent(zoneName)}/boost`, {
            method: 'POST',
            body: JSON.stringify(body),
        });
    },

    cancelBoost(zoneName) {
        return this._fetch(`/api/zones/${encodeURIComponent(zoneName)}/boost/cancel`, {
            method: 'POST',
        });
    },

    toggleAdvance(zoneName) {
        return this._fetch(`/api/zones/${encodeURIComponent(zoneName)}/advance`, {
            method: 'POST',
        });
    },
};
