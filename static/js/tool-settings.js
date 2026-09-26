const SETTINGS_TOOL_ICONS = {
  alert: '<path d="M12 3 2 20h20L12 3z"/><line x1="12" y1="10" x2="12" y2="14"/><line x1="12" y1="17.5" x2="12" y2="17.5"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="16" y2="17"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
  puzzle: '<path d="M19.4 13.5H18a2 2 0 1 1 0-4h1.4a1.6 1.6 0 0 0 1.6-1.6V5a2 2 0 0 0-2-2h-2.9a1.6 1.6 0 0 0-1.6 1.6V6a2 2 0 1 1-4 0V4.6A1.6 1.6 0 0 0 8.9 3H6a2 2 0 0 0-2 2v3a1.5 1.5 0 0 0 1.5 1.5H7a2 2 0 1 1 0 4H5.5A1.5 1.5 0 0 0 4 15v4a2 2 0 0 0 2 2h4.5v-2a2 2 0 1 1 4 0v2H19a2 2 0 0 0 2-2v-3.9a1.6 1.6 0 0 0-1.6-1.6z"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09A1.65 1.65 0 0 0 19.4 15z"/>',
  'user-plus': '<path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="19" y1="8" x2="19" y2="14"/><line x1="16" y1="11" x2="22" y2="11"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
};
const SETTINGS_TOOL_COLORS = ['blue', 'cyan', 'green', 'amber', 'red', 'violet'];

function settingsToolIcon(key) {
  const inner = SETTINGS_TOOL_ICONS[key] || SETTINGS_TOOL_ICONS.grid;
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="icon" aria-hidden="true">${inner}</svg>`;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('toolSettings', () => ({
    tools: [],
    icons: [
      { value: 'grid', label: 'Raster' },
      { value: 'puzzle', label: 'Puzzle' },
      { value: 'monitor', label: 'Monitor' },
      { value: 'users', label: 'Personen' },
      { value: 'user-plus', label: 'Person hinzufügen' },
      { value: 'file', label: 'Dokument' },
      { value: 'alert', label: 'Warnung' },
      { value: 'settings', label: 'Einstellungen' },
    ],
    loading: true,
    busy: false,
    error: '',
    success: '',
    editorOpen: false,
    editingId: null,
    draft: {},

    blankDraft() {
      return { label: '', route: '', description: '', icon_path: 'grid', color: 'blue', active: true };
    },

    iconFor: settingsToolIcon,

    clearMessages() {
      this.error = '';
      this.success = '';
    },

    async request(url, options = {}) {
      const response = await fetch(url, options);
      if (response.status === 204) return null;
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || 'Die Änderung konnte nicht gespeichert werden.');
      return payload;
    },

    async load() {
      this.loading = true;
      this.clearMessages();
      try {
        this.tools = await this.request('/api/tools');
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },

    openCreate() {
      this.clearMessages();
      this.editingId = null;
      this.draft = this.blankDraft();
      this.editorOpen = true;
    },

    openEdit(tool) {
      this.clearMessages();
      this.editingId = tool.id;
      this.draft = {
        label: tool.label,
        route: tool.route,
        description: tool.description || '',
        icon_path: SETTINGS_TOOL_ICONS[tool.icon_path] ? tool.icon_path : 'grid',
        color: SETTINGS_TOOL_COLORS.includes(tool.color) ? tool.color : 'blue',
        active: Boolean(tool.active),
      };
      this.editorOpen = true;
    },

    closeEditor() {
      if (this.busy) return;
      this.editorOpen = false;
      this.editingId = null;
      this.draft = this.blankDraft();
    },

    async save() {
      if (this.busy) return;
      this.busy = true;
      this.clearMessages();
      const editing = this.editingId !== null;
      try {
        const saved = await this.request(editing ? `/api/tools/${this.editingId}` : '/api/tools', {
          method: editing ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.draft),
        });
        if (editing) {
          const index = this.tools.findIndex(tool => tool.id === saved.id);
          if (index !== -1) this.tools.splice(index, 1, saved);
        } else {
          this.tools.push(saved);
        }
        this.editorOpen = false;
        this.editingId = null;
        this.draft = this.blankDraft();
        this.success = editing ? 'Tool wurde gespeichert.' : 'Tool wurde hinzugefügt.';
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },

    async toggleActive(tool, active) {
      if (this.busy) return;
      const previous = tool.active;
      tool.active = active ? 1 : 0;
      this.busy = true;
      this.clearMessages();
      try {
        const saved = await this.request(`/api/tools/${tool.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active }),
        });
        Object.assign(tool, saved);
        this.success = active ? 'Tool wurde aktiviert.' : 'Tool wurde deaktiviert.';
      } catch (error) {
        tool.active = previous;
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },

    async move(index, offset) {
      const target = index + offset;
      if (this.busy || target < 0 || target >= this.tools.length) return;
      const previous = [...this.tools];
      const reordered = [...this.tools];
      [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
      this.tools = reordered;
      this.busy = true;
      this.clearMessages();
      try {
        this.tools = await this.request('/api/tools/order', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tool_ids: this.tools.map(tool => tool.id) }),
        });
        this.success = 'Reihenfolge wurde gespeichert.';
      } catch (error) {
        this.tools = previous;
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },

    async remove(tool) {
      if (this.busy || !window.confirm(`Tool „${tool.label}“ wirklich löschen?`)) return;
      this.busy = true;
      this.clearMessages();
      try {
        await this.request(`/api/tools/${tool.id}`, { method: 'DELETE' });
        this.tools = this.tools.filter(item => item.id !== tool.id);
        if (this.editingId === tool.id) {
          this.editorOpen = false;
          this.editingId = null;
          this.draft = this.blankDraft();
        }
        this.success = 'Tool wurde gelöscht.';
      } catch (error) {
        this.error = error.message;
      } finally {
        this.busy = false;
      }
    },
  }));
});
