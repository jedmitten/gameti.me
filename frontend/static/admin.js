function adminPage() {
  return {
    eventId: window.location.pathname.split('/')[2],
    adminToken: new URLSearchParams(window.location.search).get('key') || window.location.hash.slice(1) || '',
    event: null,
    adminData: null,
    loading: false,
    error: '',
    tokenInput: '',
    showDeleteConfirm: false,
    deleting: false,
    deleted: false,

    async init() {
      if (this.adminToken) {
        await this.load();
      }
    },

    async load() {
      if (!this.adminToken) return;
      this.loading = true;
      this.error = '';
      this.event = null;
      this.adminData = null;
      try {
        const headers = { 'X-Admin-Token': this.adminToken };

        const [eventRes, adminRes] = await Promise.all([
          fetch(`/api/events/${this.eventId}`),
          fetch(`/api/events/${this.eventId}/admin`, { headers }),
        ]);

        if (adminRes.status === 403) {
          throw new Error('Invalid admin token. Please check and try again.');
        }

        if (!eventRes.ok) {
          const err = await eventRes.json().catch(() => ({ detail: 'Event not found' }));
          throw new Error(err.detail || 'Failed to load event');
        }

        if (!adminRes.ok) {
          const err = await adminRes.json().catch(() => ({ detail: 'Failed to load admin data' }));
          throw new Error(err.detail || 'Failed to load admin data');
        }

        this.event = await eventRes.json();
        this.adminData = await adminRes.json();
      } catch (e) {
        this.error = e.message;
        // Reset token so the form shows again if it was an auth failure
        if (e.message.includes('Invalid admin token')) {
          this.adminToken = '';
          this.tokenInput = '';
        }
      } finally {
        this.loading = false;
      }
    },

    async deleteEvent() {
      if (this.deleting) return;
      this.deleting = true;
      try {
        const res = await fetch(`/api/events/${this.eventId}`, {
          method: 'DELETE',
          headers: { 'X-Admin-Token': this.adminToken },
        });
        if (res.status === 204 || res.ok) {
          this.deleted = true;
        } else {
          const err = await res.json().catch(() => ({ detail: 'Failed to delete event' }));
          this.error = err.detail || 'Failed to delete event';
          this.showDeleteConfirm = false;
        }
      } catch (e) {
        this.error = e.message;
        this.showDeleteConfirm = false;
      } finally {
        this.deleting = false;
      }
    },
  };
}
