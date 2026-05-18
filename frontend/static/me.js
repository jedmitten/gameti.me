function mePage() {
  return {
    sessionToken: localStorage.getItem('session_token'),
    sessionUsername: localStorage.getItem('session_username'),
    user: null,
    // NOTE: sorted by submitted_at (most recent first) because the API's
    // /api/accounts/me/events endpoint does not yet return window_start/window_end.
    // To sort by "next scheduled event", add window_start + window_end to that
    // endpoint response, then sort ascending by window_start client-side.
    events: [],
    loading: true,

    authView: 'login',

    loginUsername: '', loginPassphrase: '', loginError: '', loginLoading: false,
    regUsername: '', regEmail: '', regPassphrase: '', regError: '', regLoading: false,
    recUsername: '', recEmail: '', recError: '', recSuccess: false, recLoading: false,
    recoverToken: '', recoverPassphrase: '', recoverError: '', recoverLoading: false,

    async init() {
      const hash = window.location.hash;
      if (hash && hash.startsWith('#recover:')) {
        this.recoverToken = hash.slice('#recover:'.length);
        this.authView = 'recover-confirm';
        this.loading = false;
        return;
      }

      if (this.sessionToken) {
        try {
          const res = await fetch('/api/accounts/me', {
            headers: { 'X-Session-Token': this.sessionToken },
          });
          if (res.ok) {
            this.user = await res.json();
            await this.loadUserData();
          } else if (res.status === 401) {
            localStorage.removeItem('session_token');
            localStorage.removeItem('session_username');
            this.sessionToken = null;
          }
        } catch (e) { /* network error — show login */ }
      }
      this.loading = false;
    },

    async loadUserData() {
      try {
        const [meRes, eventsRes] = await Promise.all([
          fetch('/api/accounts/me', { headers: { 'X-Session-Token': this.sessionToken } }),
          fetch('/api/accounts/me/events', { headers: { 'X-Session-Token': this.sessionToken } }),
        ]);
        if (meRes.ok)     this.user = await meRes.json();
        if (eventsRes.ok) {
          const raw = await eventsRes.json();
          // Sort by submitted_at descending (most recent participation first).
          // Once the API includes window_start, sort ascending by window_start
          // to show "next upcoming" first instead.
          this.events = raw.sort((a, b) => new Date(b.submitted_at) - new Date(a.submitted_at));
        }
      } catch (e) { /* partial failure — keep what we have */ }
    },

    async login() {
      if (!this.loginUsername.trim() || !this.loginPassphrase.trim()) return;
      this.loginLoading = true; this.loginError = '';
      try {
        const res = await fetch('/api/accounts/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: this.loginUsername.trim(), passphrase: this.loginPassphrase }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Invalid credentials' }));
          throw new Error(err.detail || 'Login failed');
        }
        const data = await res.json();
        this._saveSession(data);
        await this.loadUserData();
        this.user = { username: data.username };
      } catch (e) { this.loginError = e.message; }
      finally { this.loginLoading = false; }
    },

    async register() {
      if (!this.regUsername.trim() || !this.regPassphrase.trim()) return;
      this.regLoading = true; this.regError = '';
      try {
        const body = { username: this.regUsername.trim(), passphrase: this.regPassphrase };
        if (this.regEmail.trim()) body.email = this.regEmail.trim();
        const res = await fetch('/api/accounts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
          throw new Error(err.detail || 'Registration failed');
        }
        const data = await res.json();
        this._saveSession(data);
        await this.loadUserData();
        this.user = { username: data.username };
      } catch (e) { this.regError = e.message; }
      finally { this.regLoading = false; }
    },

    async logout() {
      if (this.sessionToken) {
        try {
          await fetch('/api/accounts/session', {
            method: 'DELETE', headers: { 'X-Session-Token': this.sessionToken },
          });
        } catch (e) { /* ignore */ }
      }
      localStorage.removeItem('session_token');
      localStorage.removeItem('session_username');
      this.sessionToken = null; this.user = null; this.events = [];
      this.authView = 'login'; this.loginUsername = ''; this.loginPassphrase = ''; this.loginError = '';
    },

    async requestRecovery() {
      if (!this.recUsername.trim() || !this.recEmail.trim()) return;
      this.recLoading = true; this.recError = ''; this.recSuccess = false;
      try {
        const res = await fetch('/api/accounts/recovery', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: this.recUsername.trim(), email: this.recEmail.trim() }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Recovery failed' }));
          throw new Error(err.detail || 'Recovery request failed');
        }
        this.recSuccess = true;
      } catch (e) { this.recError = e.message; }
      finally { this.recLoading = false; }
    },

    async confirmRecovery() {
      if (!this.recoverPassphrase.trim() || !this.recoverToken) return;
      this.recoverLoading = true; this.recoverError = '';
      try {
        const res = await fetch('/api/accounts/recovery/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: this.recoverToken, new_passphrase: this.recoverPassphrase }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Recovery failed' }));
          throw new Error(err.detail || 'Recovery confirmation failed');
        }
        const data = await res.json();
        this._saveSession(data);
        window.history.replaceState(null, '', window.location.pathname);
        await this.loadUserData();
      } catch (e) { this.recoverError = e.message; }
      finally { this.recoverLoading = false; }
    },

    _saveSession(data) {
      localStorage.setItem('session_token', data.session_token);
      localStorage.setItem('session_username', data.username);
      this.sessionToken = data.session_token;
    },

    // ── Event card helpers ─────────────────────────────────────────

    _evDate(ev) {
      // Use submitted_at as the date anchor until API exposes window_start
      return new Date(ev.submitted_at);
    },

    evMonth(ev) {
      return this._evDate(ev).toLocaleString('en-US', { month: 'short' });
    },

    evDay(ev) {
      return this._evDate(ev).getDate();
    },

    evMeta(ev) {
      const d = this._evDate(ev);
      const now = new Date();
      const diffMs = now - d;
      const diffDays = Math.floor(diffMs / 86400000);
      if (diffDays === 0) return 'Responded today';
      if (diffDays === 1) return 'Responded yesterday';
      if (diffDays < 7)  return `Responded ${diffDays} days ago`;
      return 'Responded ' + d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    },
  };
}
