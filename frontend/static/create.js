function createEvent() {
  return {
    step: 'form',
    loading: false,
    error: '',

    title: '',
    description: '',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    window_start: '',
    window_end: '',
    day_start_hour: 8,
    day_end_hour: 21,

    pickerStep: 'start',
    pickerYear: new Date().getFullYear(),
    pickerMonth: new Date().getMonth(),

    dragging: null,
    _dragCleanup: null,

    result: null,
    copiedShare: false,
    copiedAdmin: false,

    init() {
      this.$nextTick(() => this.updateFill());
    },

    // ── Date picker ──────────────────────────────────────────────

    get todayStr() {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    },

    get canGoPrev() {
      const now = new Date();
      return !(this.pickerYear === now.getFullYear() && this.pickerMonth === now.getMonth());
    },

    get pickerMonthLabel() {
      return new Date(this.pickerYear, this.pickerMonth).toLocaleString('default', { month: 'long', year: 'numeric' });
    },

    get pickerCells() {
      const first = new Date(this.pickerYear, this.pickerMonth, 1);
      const days  = new Date(this.pickerYear, this.pickerMonth + 1, 0).getDate();
      const cells = [];
      for (let i = 0; i < first.getDay(); i++) cells.push({ blank: true });
      for (let d = 1; d <= days; d++) {
        const date = `${this.pickerYear}-${String(this.pickerMonth+1).padStart(2,'0')}-${String(d).padStart(2,'0')}`;
        cells.push({ date, day: d, blank: false });
      }
      return cells;
    },

    get rangeDays() {
      if (!this.window_start || !this.window_end) return 0;
      const a = new Date(this.window_start), b = new Date(this.window_end);
      return Math.round((b - a) / 86400000) + 1;
    },

    prevMonth() {
      if (!this.canGoPrev) return;
      if (this.pickerMonth === 0) { this.pickerMonth = 11; this.pickerYear--; }
      else this.pickerMonth--;
    },

    nextMonth() {
      if (this.pickerMonth === 11) { this.pickerMonth = 0; this.pickerYear++; }
      else this.pickerMonth++;
    },

    pickDate(cell) {
      if (cell.blank || cell.date < this.todayStr) return;
      if (this.pickerStep === 'start') {
        this.window_start = cell.date;
        this.window_end   = '';
        this.pickerStep   = 'end';
      } else {
        if (cell.date < this.window_start) {
          this.window_end   = this.window_start;
          this.window_start = cell.date;
        } else {
          this.window_end = cell.date;
        }
        this.pickerStep = 'start';
      }
    },

    clearDates() {
      this.window_start = '';
      this.window_end   = '';
      this.pickerStep   = 'start';
    },

    getCellClass(cell) {
      if (cell.blank) return 'cal-cell blank';
      let cls = 'cal-cell';
      if (cell.date < this.todayStr) return cls + ' past';
      if (cell.date === this.todayStr) cls += ' today';
      if (this.window_start && this.window_end) {
        if (cell.date === this.window_start) cls += ' range-start';
        else if (cell.date === this.window_end) cls += ' range-end';
        else if (cell.date > this.window_start && cell.date < this.window_end) cls += ' in-range';
      } else if (cell.date === this.window_start) {
        cls += ' selected';
      }
      return cls;
    },

    fmtDate(iso) {
      if (!iso) return '';
      const [y, m, d] = iso.split('-');
      return new Date(+y, +m-1, +d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    },

    // ── Time range slider ─────────────────────────────────────────

    isInRange(h) {
      return h >= this.day_start_hour && h < this.day_end_hour;
    },

    formatHour(h) {
      if (h === 0)  return '12am';
      if (h < 12)  return h + 'am';
      if (h === 12) return '12pm';
      return (h - 12) + 'pm';
    },

    _hourFromX(x) {
      const track = document.getElementById('time-track');
      if (!track) return 0;
      const rect = track.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (x - rect.left) / rect.width));
      return Math.round(ratio * 24);
    },

    trackClick(e) {
      // Only fire if click is directly on track / fill (not on a pill)
      if (e.target.classList.contains('time-handle-pill')) return;
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const h = this._hourFromX(clientX);
      // Snap to whichever handle is closer
      const distStart = Math.abs(h - this.day_start_hour);
      const distEnd   = Math.abs(h - this.day_end_hour);
      if (distStart <= distEnd) {
        this.day_start_hour = Math.min(h, this.day_end_hour - 1);
      } else {
        this.day_end_hour = Math.max(h, this.day_start_hour + 1);
      }
      this.updateFill();
    },

    startDrag(which, e) {
      this.dragging = which;
      const move = (ev) => {
        const clientX = ev.touches ? ev.touches[0].clientX : ev.clientX;
        const h = this._hourFromX(clientX);
        if (which === 'start') {
          this.day_start_hour = Math.max(0, Math.min(h, this.day_end_hour - 1));
        } else {
          this.day_end_hour = Math.min(24, Math.max(h, this.day_start_hour + 1));
        }
        this.updateFill();
      };
      const up = () => {
        this.dragging = null;
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
        document.removeEventListener('touchmove', move);
        document.removeEventListener('touchend', up);
      };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
      document.addEventListener('touchmove', move, { passive: false });
      document.addEventListener('touchend', up);
    },

    updateFill() {
      const fill = document.getElementById('time-fill');
      const track = document.getElementById('time-track');
      if (!fill || !track) return;
      const pct = (v) => (v / 24 * 100).toFixed(2) + '%';
      fill.style.left  = pct(this.day_start_hour);
      fill.style.width = pct(this.day_end_hour - this.day_start_hour);
    },

    // ── Validation & submit ───────────────────────────────────────

    get canSubmit() {
      return this.title.trim() && this.window_start && this.window_end && this.day_end_hour > this.day_start_hour;
    },

    goConfirm() {
      if (!this.canSubmit) return;
      this.error = '';
      this.step = 'confirm';
    },

    async submit() {
      if (this.loading) return;
      this.loading = true;
      this.error = '';
      try {
        const res = await fetch('/api/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title:          this.title.trim(),
            description:    this.description.trim() || null,
            timezone:       this.timezone,
            window_start:   this.window_start,
            window_end:     this.window_end,
            day_start_hour: this.day_start_hour,
            day_end_hour:   this.day_end_hour,
          })
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({ detail: 'Server error' }));
          throw new Error(err.detail || 'Failed to create event');
        }
        this.result = await res.json();
        this.step = 'success';
      } catch (e) {
        this.error = e.message;
        this.step = 'confirm';
      } finally {
        this.loading = false;
      }
    },

    async copy(text, field) {
      await navigator.clipboard.writeText(text);
      this[field] = true;
      setTimeout(() => { this[field] = false; }, 2000);
    },
  };
}

// Keep fill updated when Alpine reactivity triggers re-renders
document.addEventListener('alpine:initialized', () => {
  // Observe mutations that might resize the track
  const obs = new ResizeObserver(() => {
    const comp = document.querySelector('[x-data]')?._x_dataStack?.[0];
    if (comp && comp.updateFill) comp.updateFill();
  });
  const track = document.getElementById('time-track');
  if (track) obs.observe(track);
});
