// Alpine component for the main page.
// Registered via the alpine:init event -> works regardless of when Alpine
// starts (see script order in base.html).

// Small inline-SVG icon set for tool cards, keyed by the tool's icon_path.
// Mirrors templates/_icons.html so both the server-rendered nav and these
// client-rendered cards (added/edited live via the API, without a reload)
// use the same look.
const TOOL_ICONS = {
  siren: '<path d="M12 3 2 20h20L12 3z"/><line x1="12" y1="10" x2="12" y2="14"/><line x1="12" y1="17.5" x2="12" y2="17.5"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
};

function iconFor(tool) {
  const inner = TOOL_ICONS[tool.icon_path] || TOOL_ICONS.grid;
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon">${inner}</svg>`;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('indexPage', (initialTools = []) => ({

    // --- State ---
    tools: initialTools,        // on load: active only (from Jinja)
    editing: false,
    draft: { label: '', route: '', icon_path: '', description: '' },

    // --- Derived: only the active buttons for display ---
    get activeTools() {
      return this.tools.filter(t => t.active);
    },

    iconFor,

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
        this.draft = { label: '', route: '', icon_path: '', description: '' };
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