function eventPage() {
  return {
    eventId: window.location.pathname.split('/')[2],
    event: null,
    loading: true,
    error: '',
    activeTab: 'submit',

    // Submit tab state
    submitStep: 'name',
    name: '',
    nameChecking: false,
    nameError: '',
    nameRegistered: false,

    // Registration inline
    wantRegister: false,
    regEmail: '',
    regPassphrase: '',

    // Sign-in inline
    signInPassphrase: '',
    signInError: '',

    // Session
    sessionToken: localStorage.getItem('session_token'),
    sessionUsername: localStorage.getItem('session_username'),

    // Calendar state
    selectedDays: {},
    hours: {},

    // Calendar drag
    isDragging: false,
    dragStart: null,
    dragMode: null,

    // Submission result
    editToken: null,
    copiedEdit: false,
    submitting: false,
    submitError: '',

    // Results tab state
    results: null,
    resultsLoading: false,
    selectedResultDay: null,
    resultsInterval: null,

    async init() {
      try {
        const res = await fetch(`/api/events/${this.eventId}`);
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Event not found' }));
          this.error = err.detail || 'Failed to load event';
          this.loading = false;
          return;
        }
        this.event = await res.json();

        // Try to load existing submission if session exists
        if (this.sessionToken) {
          try {
            const subRes = await fetch(`/api/events/${this.eventId}/submissions/me`, {
              headers: { 'X-Session-Token': this.sessionToken }
            });
            if (subRes.ok) {
              const subData = await subRes.json();
              this._loadSubmission(subData);
              this.name = this.sessionUsername || '';
              this.submitStep = 'calendar';
            } else if (subRes.status === 401) {
              // Session expired
              localStorage.removeItem('session_token');
              localStorage.removeItem('session_username');
              this.sessionToken = null;
              this.sessionUsername = null;
            }
          } catch (e) {
            // Ignore — user hasn't submitted yet
          }
        }
      } catch (e) {
        this.error = 'Failed to load event. Please try again.';
      }
      this.loading = false;

      // Add global mouseup listener for drag
      window.addEventListener('mouseup', () => { this.isDragging = false; });
    },

    _loadSubmission(data) {
      if (!data || !data.availability) return;
      const newHours = {};
      const newDays = {};
      for (const slot of data.availability) {
        newDays[slot.date] = true;
        if (!newHours[slot.date]) newHours[slot.date] = {};
        newHours[slot.date][slot.hour] = slot.status;
      }
      this.selectedDays = newDays;
      this.hours = newHours;
    },

    // Computed: months in range
    get visibleMonths() {
      if (!this.event) return [];
      const months = [];
      const start = new Date(this.event.window_start + 'T00:00:00');
      const end = new Date(this.event.window_end + 'T00:00:00');
      const todayStr = new Date().toISOString().slice(0, 10);

      let year = start.getFullYear();
      let month = start.getMonth();
      const endYear = end.getFullYear();
      const endMonth = end.getMonth();

      while (year < endYear || (year === endYear && month <= endMonth)) {
        const first = new Date(year, month, 1);
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const startDow = first.getDay();
        const label = first.toLocaleString('default', { month: 'long', year: 'numeric' });

        const cells = [];
        for (let i = 0; i < startDow; i++) cells.push({ blank: true, inWindow: false });
        for (let d = 1; d <= daysInMonth; d++) {
          const date = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
          const inWindow = date >= this.event.window_start && date <= this.event.window_end;
          cells.push({
            blank: false,
            date,
            day: d,
            inWindow,
            isSelected: !!this.selectedDays[date],
            isToday: date === todayStr,
          });
        }

        months.push({ year, month, label, cells });

        month++;
        if (month > 11) { month = 0; year++; }
      }

      return months;
    },

    get availableHours() {
      if (!this.event) return [];
      const hrs = [];
      for (let h = this.event.day_start_hour; h < this.event.day_end_hour; h++) {
        hrs.push(h);
      }
      return hrs;
    },

    get sortedSelectedDays() {
      return Object.keys(this.selectedDays).filter(d => this.selectedDays[d]).sort();
    },

    get submissionSummary() {
      let yes = 0, maybe = 0, no = 0;
      for (const date of Object.keys(this.hours)) {
        for (const hour of Object.keys(this.hours[date])) {
          const s = this.hours[date][hour];
          if (s === 'yes') yes++;
          else if (s === 'maybe') maybe++;
          else if (s === 'no') no++;
        }
      }
      return { days: this.sortedSelectedDays.length, yes, maybe, no };
    },

    get canSubmit() {
      const summary = this.submissionSummary;
      const hasSlots = summary.yes + summary.maybe + summary.no > 0;
      const hasName = (this.name && this.name.trim()) || this.sessionUsername;
      return hasSlots && hasName && !this.submitting;
    },

    get topSlots() {
      if (!this.results || !this.results.slots) return [];
      return [...this.results.slots]
        .sort((a, b) => b.score - a.score)
        .slice(0, 5);
    },

    async checkName() {
      // If already signed in via session, skip to calendar
      if (this.sessionUsername) {
        this.name = this.sessionUsername;
        this.submitStep = 'calendar';
        return;
      }

      if (!this.name.trim()) return;
      this.nameChecking = true;
      this.nameError = '';
      try {
        const res = await fetch('/api/accounts/check-username', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: this.name.trim() })
        });
        if (!res.ok) throw new Error('Failed to check name');
        const data = await res.json();
        if (!data.available) {
          // Name is registered — show sign-in
          this.nameRegistered = true;
          this.submitStep = 'auth';
        } else {
          // Name is free — proceed to calendar
          this.submitStep = 'calendar';
        }
      } catch (e) {
        this.nameError = e.message;
      } finally {
        this.nameChecking = false;
      }
    },

    toggleDay(date) {
      if (this.selectedDays[date]) {
        // Deselect
        const newDays = { ...this.selectedDays };
        delete newDays[date];
        this.selectedDays = newDays;
        const newHours = { ...this.hours };
        delete newHours[date];
        this.hours = newHours;
      } else {
        this.selectedDays = { ...this.selectedDays, [date]: true };
        if (!this.hours[date]) {
          this.hours = { ...this.hours, [date]: {} };
        }
      }
    },

    startDrag(cell) {
      this.isDragging = true;
      this.dragStart = cell.date;
      this.dragMode = this.selectedDays[cell.date] ? 'deselect' : 'select';
    },

    continueDrag(cell) {
      if (!this.isDragging) return;
      if (this.dragMode === 'select' && !this.selectedDays[cell.date]) {
        this.selectedDays = { ...this.selectedDays, [cell.date]: true };
        if (!this.hours[cell.date]) {
          this.hours = { ...this.hours, [cell.date]: {} };
        }
      } else if (this.dragMode === 'deselect' && this.selectedDays[cell.date]) {
        const newDays = { ...this.selectedDays };
        delete newDays[cell.date];
        this.selectedDays = newDays;
        const newHours = { ...this.hours };
        delete newHours[cell.date];
        this.hours = newHours;
      }
    },

    toggleHour(date, hour) {
      const current = (this.hours[date] && this.hours[date][hour]) || 'unset';
      const cycle = { 'unset': 'yes', 'yes': 'maybe', 'maybe': 'no', 'no': 'unset' };
      const next = cycle[current];
      const dateHours = { ...(this.hours[date] || {}) };
      if (next === 'unset') {
        delete dateHours[hour];
      } else {
        dateHours[hour] = next;
      }
      this.hours = { ...this.hours, [date]: dateHours };
    },

    markAllDay(date, status) {
      const dateHours = {};
      if (status !== 'unset') {
        for (const h of this.availableHours) {
          dateHours[h] = status;
        }
      }
      this.hours = { ...this.hours, [date]: dateHours };
    },

    async submit() {
      if (!this.canSubmit || this.submitting) return;
      this.submitting = true;
      this.submitError = '';
      try {
        // Build availability array
        const availability = [];
        for (const date of Object.keys(this.hours)) {
          for (const hourStr of Object.keys(this.hours[date])) {
            const status = this.hours[date][hourStr];
            if (status && status !== 'unset') {
              availability.push({ date, hour: parseInt(hourStr, 10), status });
            }
          }
        }

        const body = {
          name: this.name.trim(),
          availability,
        };

        if (this.wantRegister && !this.sessionUsername) {
          body.register = true;
          if (this.regEmail) body.email = this.regEmail;
          if (this.regPassphrase) body.passphrase = this.regPassphrase;
        }

        const headers = { 'Content-Type': 'application/json' };
        if (this.sessionToken) headers['X-Session-Token'] = this.sessionToken;

        const res = await fetch(`/api/events/${this.eventId}/submissions`, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
        });

        if (res.status === 409) {
          const err = await res.json().catch(() => ({}));
          if (err.registered) {
            this.nameRegistered = true;
            this.submitStep = 'auth';
            this.submitting = false;
            return;
          }
          throw new Error(err.message || 'Conflict error');
        }

        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Server error' }));
          throw new Error(err.detail || 'Failed to submit');
        }

        const data = await res.json();
        this.editToken = data.edit_token || null;

        // If we registered, save session
        if (data.session_token) {
          localStorage.setItem('session_token', data.session_token);
          localStorage.setItem('session_username', this.name.trim());
          this.sessionToken = data.session_token;
          this.sessionUsername = this.name.trim();
        }

        this.submitStep = 'done';
      } catch (e) {
        this.submitError = e.message;
      } finally {
        this.submitting = false;
      }
    },

    async signIn() {
      if (!this.signInPassphrase.trim()) return;
      this.signInError = '';
      try {
        const res = await fetch('/api/accounts/session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username: this.name.trim(), passphrase: this.signInPassphrase }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Invalid credentials' }));
          throw new Error(err.detail || 'Sign in failed');
        }
        const data = await res.json();
        localStorage.setItem('session_token', data.session_token);
        localStorage.setItem('session_username', data.username);
        this.sessionToken = data.session_token;
        this.sessionUsername = data.username;
        this.name = data.username;
        this.submitStep = 'calendar';
      } catch (e) {
        this.signInError = e.message;
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
      this.name = '';
      this.submitStep = 'name';
    },

    async loadResults() {
      this.resultsLoading = true;
      try {
        const res = await fetch(`/api/events/${this.eventId}/results`);
        if (res.ok) {
          this.results = await res.json();
        }
      } catch (e) { /* ignore */ }
      this.resultsLoading = false;
    },

    async switchTab(tab) {
      if (tab === this.activeTab) return;
      if (tab === 'results') {
        this.activeTab = tab;
        await this.loadResults();
        this.resultsInterval = setInterval(() => this.loadResults(), 30000);
      } else {
        if (this.resultsInterval) {
          clearInterval(this.resultsInterval);
          this.resultsInterval = null;
        }
        this.activeTab = tab;
      }
    },

    resetSubmit() {
      this.submitStep = 'name';
      this.name = this.sessionUsername || '';
      this.selectedDays = {};
      this.hours = {};
      this.editToken = null;
      this.submitError = '';
      this.wantRegister = false;
      this.regEmail = '';
      this.regPassphrase = '';
    },

    async copyEditToken() {
      if (!this.editToken) return;
      await navigator.clipboard.writeText(this.editToken);
      this.copiedEdit = true;
      setTimeout(() => { this.copiedEdit = false; }, 2000);
    },

    formatHour(h) {
      if (h === 0) return '12am';
      if (h < 12) return h + 'am';
      if (h === 12) return '12pm';
      return (h - 12) + 'pm';
    },

    formatDateLabel(date) {
      if (!date) return '';
      const d = new Date(date + 'T00:00:00');
      return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    },

    getCalCellClass(cell) {
      if (cell.blank) return 'cal-cell blank';
      let cls = 'cal-cell';
      if (!cell.inWindow) cls += ' out-window';
      else {
        cls += ' in-window';
        if (this.selectedDays[cell.date]) cls += ' selected';
        if (cell.isToday) cls += ' today';
      }
      return cls;
    },

    getHourCellClass(date, hour) {
      const status = (this.hours[date] && this.hours[date][hour]) || 'unset';
      return `hour-cell status-${status}`;
    },

    getResultCellClass(cell) {
      if (cell.blank) return 'cal-cell blank';
      let cls = 'cal-cell';
      if (!cell.inWindow) {
        cls += ' out-window';
      } else {
        cls += ' in-window';
        const heat = this.getDayHeatClass(cell.date);
        if (heat) cls += ' ' + heat;
        if (cell.date === this.selectedResultDay) cls += ' selected';
        if (cell.isToday) cls += ' today';
      }
      return cls;
    },

    getDayHeatClass(date) {
      if (!this.results || !this.results.slots) return '';
      const daySlots = this.results.slots.filter(s => s.date === date);
      if (daySlots.length === 0) return 'heat-none';
      const totalScore = daySlots.reduce((sum, s) => sum + s.score, 0);
      if (totalScore > 4) return 'heat-high';
      if (totalScore > 0) return 'heat-med';
      return 'heat-low';
    },

    getDaySlots(date) {
      if (!date || !this.results || !this.results.slots) return [];
      return this.results.slots.filter(s => s.date === date).sort((a, b) => a.hour - b.hour);
    },
  };
}
