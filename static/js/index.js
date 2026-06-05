// Alpine component for the main page.
// Registered via the alpine:init event -> works regardless of when Alpine
// starts (see script order in base.html).

document.addEventListener('alpine:init', () => {
  Alpine.data('indexPage', (initialTools = []) => ({

    // --- State ---
    tools: initialTools,        // on load: active only (from Jinja)
    editing: false,
    draft: { label: '', route: '', icon_path: '' },

    // --- Derived: only the active buttons for display ---
    get activeTools() {
      return this.tools.filter(t => t.active);
    },

    // --- Toggle edit mode ---
    toggleEditing() {
      this.editing = !this.editing;
      // In edit mode load ALL buttons (including hidden ones)
      // so they can be re-enabled.
      if (this.editing) this.reload();
    },

    // --- Fetch the current state fresh from the server ---
    async reload() {
      const r = await fetch('/api/tools');
      if (r.ok) this.tools = await r.json();
    },

    // --- Add a new button ---
    async add() {
      const r = await fetch('/api/tools', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(this.draft),
      });
      if (r.ok) {
        const tool = await r.json();     // server returns the finished object
        this.tools.push(tool);           // -> display follows automatically (reactivity)
        this.draft = { label: '', route: '', icon_path: '' };
      } else {
        alert('Failed to add tool.');
      }
    },

    // --- Update individual fields of a button ---
    async update(tool, fields) {
      const r = await fetch(`/api/tools/${tool.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(fields),
      });
      if (r.ok) {
        const updated = await r.json();
        Object.assign(tool, updated);    // align the local entry with the server state
      } else {
        alert('Update failed.');
      }
    },

    // --- Delete a button ---
    async remove(tool) {
      if (!confirm(`Really delete "${tool.label}"?`)) return;
      const r = await fetch(`/api/tools/${tool.id}`, { method: 'DELETE' });
      if (r.ok) {
        this.tools = this.tools.filter(t => t.id !== tool.id);
      } else {
        alert('Delete failed.');
      }
    },

  }));
});