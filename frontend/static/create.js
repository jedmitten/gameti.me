function createEvent() {
  return {
    step: 'form',
    loading: false,
    error: '',

    // Form fields
    title: '',
    description: '',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    window_start: '',
    window_end: '',
    day_start_hour: 8,
    day_end_hour: 21,

    // Date picker state
    pickerStep: 'start',
    pickerYear: new Date().getFullYear(),
    pickerMonth: new Date().getMonth(),

    // Result
    result: null,
    copiedShare: false,
    copiedAdmin: false,

    init() {},

    get pickerMonthLabel() {
      return new Date(this.pickerYear, this.pickerMonth).toLocaleString('default', { month: 'long', year: 'numeric' });
    },

    get pickerCells() {
      const first = new Date(this.pickerYear, this.pickerMonth, 1);
      const daysInMonth = new Date(this.pickerYear, this.pickerMonth + 1, 0).getDate();
      const startDow = first.getDay();
      const cells = [];
      for (let i = 0; i < startDow; i++) cells.push({ blank: true });
      for (let d = 1; d <= daysInMonth; d++) {
        const date = `${this.pickerYear}-${String(this.pickerMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        cells.push({ date, day: d, blank: false });
      }
      return cells;
    },

    prevMonth() {
      if (this.pickerMonth === 0) { this.pickerMonth = 11; this.pickerYear--; }
      else { this.pickerMonth--; }
    },

    nextMonth() {
      if (this.pickerMonth === 11) { this.pickerMonth = 0; this.pickerYear++; }
      else { this.pickerMonth++; }
    },

    pickDate(cell) {
      if (cell.blank) return;
      if (this.pickerStep === 'start') {
        this.window_start = cell.date;
        this.window_end = '';
        this.pickerStep = 'end';
      } else {
        if (cell.date < this.window_start) {
          this.window_end = this.window_start;
          this.window_start = cell.date;
        } else {
          this.window_end = cell.date;
        }
        this.pickerStep = 'start';
      }
    },

    getCellClass(cell) {
      if (cell.blank) return 'cal-cell blank';
      let cls = 'cal-cell';
      if (cell.date === this.window_start && this.window_end) cls += ' range-start';
      else if (cell.date === this.window_end) cls += ' range-end';
      else if (cell.date === this.window_start) cls += ' selected';
      else if (this.window_start && this.window_end && cell.date > this.window_start && cell.date < this.window_end) cls += ' in-range';
      return cls;
    },

    get pickerInstructions() {
      if (this.window_start && this.window_end) {
        return `Range: ${this.window_start} to ${this.window_end}`;
      }
      if (this.pickerStep === 'start' && !this.window_start) return 'Click to set start date';
      if (this.pickerStep === 'end') return 'Click to set end date';
      return 'Click to set start date';
    },

    get hourOptions() {
      const opts = [];
      for (let h = 0; h <= 23; h++) opts.push({ value: h, label: this.formatHour(h) });
      return opts;
    },

    formatHour(h) {
      if (h === 0) return '12am';
      if (h < 12) return h + 'am';
      if (h === 12) return '12pm';
      return (h - 12) + 'pm';
    },

    get canSubmit() {
      return this.title.trim() && this.window_start && this.window_end && this.day_end_hour > this.day_start_hour;
    },

    async submit() {
      if (!this.canSubmit || this.loading) return;
      this.loading = true;
      this.error = '';
      try {
        const res = await fetch('/api/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: this.title.trim(),
            description: this.description.trim() || null,
            timezone: this.timezone,
            window_start: this.window_start,
            window_end: this.window_end,
            day_start_hour: this.day_start_hour,
            day_end_hour: this.day_end_hour,
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
