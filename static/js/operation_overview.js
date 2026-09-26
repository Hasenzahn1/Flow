window.addEventListener('pageshow', (event) => {
  if (event.persisted) window.location.reload();
});

document.addEventListener('alpine:init', () => {
  Alpine.data('selectionPage', (operations = []) => ({
    query: '',
    createModalOpen: false,
    newName: '',
    submitting: false,
    error: '',
    exportModalOpen: false,
    exportOperation: null,
    exportCombined: true,
    exportError: '',
    exportSections: {
      patients: true,
      helpers_summary: true,
      helpers_detail: true,
      vehicles: true,
    },

    rows: operations.map((operation) => ({
      ...operation,
      participant_count: operation.participant_count || 0,
      formattedDate: operation.date
        ? new Date(operation.date * 1000).toLocaleDateString('de-DE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
          })
        : '—',
    })),

    get filteredRows() {
      const needle = this.query.trim().toLocaleLowerCase('de-DE');
      if (!needle) return this.rows;
      return this.rows.filter((row) => row.name.toLocaleLowerCase('de-DE').includes(needle));
    },

    openOperation(id) {
      window.location.href = `/operation_overview/${id}`;
    },

    openCreateModal() {
      this.createModalOpen = true;
      this.error = '';
      this.$nextTick(() => this.$refs.nameInput.focus());
    },

    closeCreateModal() {
      if (this.submitting) return;
      this.createModalOpen = false;
      this.newName = '';
      this.error = '';
    },

    openExportModal(operation) {
      this.exportOperation = operation;
      this.exportCombined = true;
      this.exportError = '';
      this.exportSections = {
        patients: true,
        helpers_summary: true,
        helpers_detail: true,
        vehicles: true,
      };
      this.exportModalOpen = true;
    },

    closeExportModal() {
      this.exportModalOpen = false;
      this.exportOperation = null;
      this.exportError = '';
    },

    submitExport() {
      if (!this.exportOperation) return;
      const selected = Object.entries(this.exportSections)
        .filter(([, enabled]) => enabled)
        .map(([section]) => section);
      if (!selected.length) {
        this.exportError = 'Bitte mindestens einen Exportbereich auswählen.';
        return;
      }
      const params = new URLSearchParams();
      selected.forEach(section => params.append('section', section));
      params.set('bundle', this.exportCombined ? 'pdf' : 'zip');
      window.location.href = `/api/operation_overview/${this.exportOperation.id}/export?${params}`;
      this.closeExportModal();
    },

    async createOperation() {
      const name = this.newName.trim();
      if (!name || this.submitting) return;

      this.submitting = true;
      this.error = '';
      try {
        const response = await fetch('/api/operation_overview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });

        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.error || 'Die Lage konnte nicht erstellt werden.');
        }

        const operation = await response.json();
        window.location.href = `/operation_overview/${operation.id}`;
      } catch (error) {
        this.error = error.message || 'Die Lage konnte nicht erstellt werden.';
        this.submitting = false;
      }
    },
  }));
});
