function mePage() {
  return {
    sessionToken: localStorage.getItem('session_token'),
    sessionUsername: localStorage.getItem('session_username'),
    user: null,
    events: [],
    loading: true,

    // Auth panels
    authView: 'login',

    // Login form
    loginUsername: '',
    loginPassphrase: '',
    loginError: '',
    loginLoading: false,

    // Register form
    regUsername: '',
    regEmail: '',
    regPassphrase: '',
    regError: '',
    regLoading: false,

    // Recovery
    recUsername: '',
    recEmail: '',
    recError: '',
    recSuccess: false,
    recLoading: false,

    // Recovery confirm
    recoverToken: '',
    recoverPassphrase: '',
    recoverError: '',
    recoverLoading: false,

    async init() {
      // Check for recovery link in URL hash
      const hash = window.location.hash;
      if (hash && hash.startsWith('#recover:')) {
        this.recoverToken = hash.slice('#recover:'.length);
        this.authView = 'recover-confirm';
        this.loading = false;
        return;
      }

      // If session token exists, try to load user
      if (this.sessionToken) {
        try {
          const res = await fetch('/api/accounts/me', {
            headers: { 'X-Session-Token': this.sessionToken },
          });
          if (res.ok) {
            this.user = await res.json();
            await this.loadUserData();
          } else if (res.status === 401) {
            // Expired/invalid session
            localStorage.removeItem('session_token');
            localStorage.removeItem('session_username');
            this.sessionToken = null;
            this.sessionUsername = null;
          }
        } catch (e) {
          // Network error — just show login
        }
      }

      this.loading = false;
    },

    async login() {
      if (!this.loginUsername.trim() || !this.loginPassphrase.trim()) return;
      this.loginLoading = true;
      this.loginError = '';
      try {
        const res = await fetch('/api/accounts/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: this.loginUsername.trim(),
            passphrase: this.loginPassphrase,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Invalid credentials' }));
          throw new Error(err.detail || 'Login failed');
        }
        const data = await res.json();
        localStorage.setItem('session_token', data.session_token);
        localStorage.setItem('session_username', data.username);
        this.sessionToken = data.session_token;
        this.sessionUsername = data.username;
        await this.loadUserData();
        this.user = { username: data.username };
      } catch (e) {
        this.loginError = e.message;
      } finally {
        this.loginLoading = false;
      }
    },

    async register() {
      if (!this.regUsername.trim() || !this.regPassphrase.trim()) return;
      this.regLoading = true;
      this.regError = '';
      try {
        const body = {
          username: this.regUsername.trim(),
          passphrase: this.regPassphrase,
        };
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
        localStorage.setItem('session_token', data.session_token);
        localStorage.setItem('session_username', data.username);
        this.sessionToken = data.session_token;
        this.sessionUsername = data.username;
        await this.loadUserData();
        this.user = { username: data.username };
      } catch (e) {
        this.regError = e.message;
      } finally {
        this.regLoading = false;
      }
    },

    async logout() {
      if (this.sessionToken) {
        try {
          await fetch('/api/accounts/session', {
            method: 'DELETE',
            headers: { 'X-Session-Token': this.sessionToken },
          });
        } catch (e) { /* ignore */ }
      }
      localStorage.removeItem('session_token');
      localStorage.removeItem('session_username');
      this.sessionToken = null;
      this.sessionUsername = null;
      this.user = null;
      this.events = [];
      this.authView = 'login';
      this.loginUsername = '';
      this.loginPassphrase = '';
      this.loginError = '';
    },

    async loadUserData() {
      try {
        const [meRes, eventsRes] = await Promise.all([
          fetch('/api/accounts/me', { headers: { 'X-Session-Token': this.sessionToken } }),
          fetch('/api/accounts/me/events', { headers: { 'X-Session-Token': this.sessionToken } }),
        ]);
        if (meRes.ok) {
          this.user = await meRes.json();
        }
        if (eventsRes.ok) {
          this.events = await eventsRes.json();
        }
      } catch (e) {
        // Partial failure — keep what we have
      }
    },

    async requestRecovery() {
      if (!this.recUsername.trim() || !this.recEmail.trim()) return;
      this.recLoading = true;
      this.recError = '';
      this.recSuccess = false;
      try {
        const res = await fetch('/api/accounts/recovery', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: this.recUsername.trim(),
            email: this.recEmail.trim(),
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Recovery failed' }));
          throw new Error(err.detail || 'Recovery request failed');
        }
        this.recSuccess = true;
      } catch (e) {
        this.recError = e.message;
      } finally {
        this.recLoading = false;
      }
    },

    async confirmRecovery() {
      if (!this.recoverPassphrase.trim() || !this.recoverToken) return;
      this.recoverLoading = true;
      this.recoverError = '';
      try {
        const res = await fetch('/api/accounts/recovery/confirm', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            token: this.recoverToken,
            new_passphrase: this.recoverPassphrase,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Recovery failed' }));
          throw new Error(err.detail || 'Recovery confirmation failed');
        }
        const data = await res.json();
        localStorage.setItem('session_token', data.session_token);
        localStorage.setItem('session_username', data.username);
        this.sessionToken = data.session_token;
        this.sessionUsername = data.username;
        // Clear hash
        window.history.replaceState(null, '', window.location.pathname);
        await this.loadUserData();
      } catch (e) {
        this.recoverError = e.message;
      } finally {
        this.recoverLoading = false;
      }
    },

    formatDate(iso) {
      if (!iso) return '';
      try {
        return new Date(iso).toLocaleDateString('en-US', {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        });
      } catch (e) {
        return iso;
      }
    },
  };
}
