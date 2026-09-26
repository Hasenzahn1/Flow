const vehicleSocket = window.socket;

function blankVehicle() {
  return { call_sign: '', vehicle_type: '', phone: '', target_occupancy: 1, max_seats: 1 };
}

document.addEventListener('alpine:init', () => {
  Alpine.data('vehiclesPage', operationId => ({
    operationId,
    vehicles: [],
    helpers: [],
    stats: { occupied: 0, max_seats: 0, statuses: {} },
    templateCount: 0,
    templates: [],
    query: '',
    typeFilter: '',
    statusFilter: '',
    statusOptions: ['Unbesetzt', 'Unvollständig', 'Gut besetzt', 'Voll', 'Überbelegt'],
    suggestedTypes: ['KTW', 'RTW', 'NEF', 'MTW', 'KdoW', 'ELW', 'LF', 'HLF', 'GW-San'],
    loading: false,
    saving: false,
    vehicleModalOpen: false,
    crewModalOpen: false,
    saveTemplateOpen: false,
    templatesOpen: false,
    editingVehicleId: null,
    selectedVehicle: null,
    vehicleForm: blankVehicle(),
    crewQuery: '',
    templateName: '',
    modalError: '',
    toast: '',
    toastTimer: null,
    draggedId: null,

    async init() {
      await Promise.all([this.loadVehicles(), this.loadTemplates()]);
      if (vehicleSocket) {
        vehicleSocket.emit('join', { operation_id: this.operationId });
        vehicleSocket.on('vehicles_changed', event => {
          if (event.operation_id === this.operationId) this.loadVehicles();
        });
        vehicleSocket.on('vehicle_templates_changed', () => this.loadTemplates());
      }
    },

    async api(url, options = {}) {
      const response = await fetch(url, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
      });
      if (!response.ok) {
        let message = `Fehler ${response.status}`;
        try { message = (await response.json()).error || message; } catch (_) {}
        const error = new Error(message);
        error.status = response.status;
        throw error;
      }
      if (response.status === 204) return null;
      return response.json();
    },

    async loadVehicles() {
      this.loading = true;
      try {
        const result = await this.api(`/api/operation_overview/${this.operationId}/vehicles`);
        this.vehicles = result.items;
        this.helpers = result.helpers;
        this.stats = result.stats;
        this.templateCount = result.template_count;
        if (this.selectedVehicle) {
          this.selectedVehicle = this.vehicles.find(item => item.id === this.selectedVehicle.id) || null;
        }
        this.$nextTick(() => requestAnimationFrame(() => this.syncLeaderSelects()));
      } catch (error) {
        this.showToast(error.message);
      } finally {
        this.loading = false;
      }
    },

    syncLeaderSelects() {
      document.querySelectorAll('select[data-leader-vehicle]').forEach(select => {
        const vehicle = this.vehicles.find(item => item.id === Number(select.dataset.leaderVehicle));
        select.value = vehicle?.leader_id ? String(vehicle.leader_id) : '';
      });
    },

    async loadTemplates() {
      try {
        const result = await this.api('/api/vehicle-templates');
        this.templates = result.items;
        this.templateCount = this.templates.filter(item => !item.invalid).length;
      } catch (error) {
        this.showToast(error.message);
      }
    },

    get vehicleTypes() {
      return [...new Set([...this.suggestedTypes, ...this.vehicles.map(item => item.vehicle_type)])]
        .filter(Boolean).sort((a, b) => a.localeCompare(b, 'de'));
    },

    get filteredVehicles() {
      const term = this.query.trim().toLocaleLowerCase('de');
      return this.vehicles.filter(vehicle => {
        const searchable = [
          vehicle.call_sign, vehicle.vehicle_type, vehicle.phone,
          ...vehicle.crew.flatMap(person => [person.first_name, person.last_name])
        ].filter(Boolean).join(' ').toLocaleLowerCase('de');
        return (!term || searchable.includes(term))
          && (!this.typeFilter || vehicle.vehicle_type === this.typeFilter)
          && (!this.statusFilter || vehicle.status === this.statusFilter);
      });
    },

    get sortingEnabled() {
      return !this.query.trim() && !this.typeFilter && !this.statusFilter;
    },

    get occupancyPercent() {
      if (!this.stats.max_seats) return 0;
      return Math.min(100, Math.round((this.stats.occupied / this.stats.max_seats) * 100));
    },

    get seatSummary() {
      const free = this.stats.max_seats - this.stats.occupied;
      if (free >= 0) return `${free} ${free === 1 ? 'freier Platz' : 'freie Plätze'}`;
      return `${Math.abs(free)} ${free === -1 ? 'Person' : 'Personen'} über Kapazität`;
    },

    get selectableHelpers() {
      const term = this.crewQuery.trim().toLocaleLowerCase('de');
      return this.helpers.filter(helper => {
        if (helper.status !== 'Anwesend' || helper.vehicle_id !== null) return false;
        return !term || this.personName(helper).toLocaleLowerCase('de').includes(term)
          || (helper.mobile || '').toLocaleLowerCase('de').includes(term);
      });
    },

    personName(person) {
      return `${person.first_name || ''} ${person.last_name || ''}`.trim();
    },

    initials(person) {
      return `${person.first_name?.[0] || ''}${person.last_name?.[0] || ''}`.toUpperCase() || '?';
    },

    statusKey(status) {
      return {
        'Unbesetzt': 'empty', 'Unvollständig': 'incomplete', 'Gut besetzt': 'good',
        'Voll': 'full', 'Überbelegt': 'overbooked'
      }[status] || 'empty';
    },

    seatDots(vehicle) {
      const visibleSeats = Math.min(Number(vehicle.max_seats) || 0, 12);
      const occupiedSeats = Math.min(Number(vehicle.crew_count) || 0, visibleSeats);
      const isOverbooked = Number(vehicle.crew_count) > Number(vehicle.max_seats);
      return Array.from({ length: visibleSeats }, (_, index) => ({
        index,
        state: index < occupiedSeats
          ? (isOverbooked ? 'vehicle-seat--overbooked' : 'vehicle-seat--occupied')
          : (index < Number(vehicle.target_occupancy) ? 'vehicle-seat--target' : 'vehicle-seat--free')
      }));
    },

    async updatePhone(vehicle, value) {
      const phone = value.trim() || null;
      const previousPhone = vehicle.phone || null;
      if (phone === previousPhone) return;
      vehicle.phone = phone;
      try {
        const updatedVehicle = await this.api(
          `/api/operation_overview/${this.operationId}/vehicles/${vehicle.id}`,
          { method: 'PATCH', body: JSON.stringify({ phone }) }
        );
        Object.assign(vehicle, updatedVehicle);
        this.showToast('Telefonnummer gespeichert');
        this.$nextTick(() => this.syncLeaderSelects());
      } catch (error) {
        vehicle.phone = previousPhone;
        this.showToast(error.message);
      }
    },

    openVehicleModal(vehicle = null) {
      this.modalError = '';
      this.editingVehicleId = vehicle?.id || null;
      this.vehicleForm = vehicle ? {
        call_sign: vehicle.call_sign,
        vehicle_type: vehicle.vehicle_type,
        phone: vehicle.phone || '',
        target_occupancy: vehicle.target_occupancy,
        max_seats: vehicle.max_seats
      } : blankVehicle();
      this.vehicleModalOpen = true;
    },

    closeVehicleModal() {
      this.vehicleModalOpen = false;
      this.editingVehicleId = null;
      this.modalError = '';
    },

    async saveVehicle() {
      if (this.saving) return;
      if (!this.vehicleForm.call_sign.trim() || !this.vehicleForm.vehicle_type.trim()) {
        this.modalError = 'Funkrufname und Fahrzeugtyp sind Pflichtfelder.';
        return;
      }
      if (Number(this.vehicleForm.target_occupancy) > Number(this.vehicleForm.max_seats)) {
        this.modalError = 'Die Sollbesetzung darf die Maximalsitze nicht überschreiten.';
        return;
      }
      this.saving = true;
      this.modalError = '';
      const wasEditing = Boolean(this.editingVehicleId);
      const url = this.editingVehicleId
        ? `/api/operation_overview/${this.operationId}/vehicles/${this.editingVehicleId}`
        : `/api/operation_overview/${this.operationId}/vehicles`;
      try {
        await this.api(url, {
          method: this.editingVehicleId ? 'PATCH' : 'POST',
          body: JSON.stringify(this.vehicleForm)
        });
        this.closeVehicleModal();
        this.showToast(wasEditing ? 'Fahrzeug geändert' : 'Fahrzeug angelegt');
        await this.loadVehicles();
      } catch (error) {
        this.modalError = error.message;
      } finally {
        this.saving = false;
      }
    },

    async removeVehicle(vehicle) {
      if (!confirm(`Fahrzeug „${vehicle.call_sign}“ löschen? Alle Besatzungszuordnungen werden gelöst.`)) return;
      try {
        await this.api(`/api/operation_overview/${this.operationId}/vehicles/${vehicle.id}`, { method: 'DELETE' });
        this.showToast('Fahrzeug gelöscht');
        await this.loadVehicles();
      } catch (error) { this.showToast(error.message); }
    },

    openCrew(vehicle) {
      this.selectedVehicle = vehicle;
      this.crewQuery = '';
      this.crewModalOpen = true;
    },

    async setAssignment(helperId, vehicleId, role = 'member') {
      await this.api(`/api/operation_overview/${this.operationId}/vehicle-assignments/${helperId}`, {
        method: 'PUT', body: JSON.stringify({ vehicle_id: vehicleId, role })
      });
      await this.loadVehicles();
    },

    async assign(helper, role) {
      try {
        await this.setAssignment(helper.id, this.selectedVehicle.id, role);
        this.showToast(role === 'leader' ? 'Gruppenführer zugewiesen' : 'Person hinzugefügt');
        if (this.selectableHelpers.length === 0) this.crewModalOpen = false;
      } catch (error) { this.showToast(error.message); }
    },

    async unassign(person) {
      try {
        await this.setAssignment(person.id, null, 'member');
        this.showToast('Person aus Fahrzeug entfernt');
      } catch (error) { this.showToast(error.message); }
    },

    async changeLeader(vehicle, rawId) {
      const helperId = Number(rawId);
      try {
        if (!helperId) {
          if (vehicle.leader) await this.setAssignment(vehicle.leader.id, vehicle.id, 'member');
        } else {
          await this.setAssignment(helperId, vehicle.id, 'leader');
        }
        this.showToast(helperId ? 'Gruppenführer geändert' : 'Gruppenführer entfernt');
      } catch (error) { this.showToast(error.message); await this.loadVehicles(); }
    },

    startDrag(vehicleId) {
      if (this.sortingEnabled) this.draggedId = vehicleId;
    },

    async dropOn(targetId) {
      if (!this.sortingEnabled || !this.draggedId || this.draggedId === targetId) return;
      const reordered = [...this.vehicles];
      const from = reordered.findIndex(item => item.id === this.draggedId);
      const to = reordered.findIndex(item => item.id === targetId);
      const [moved] = reordered.splice(from, 1);
      reordered.splice(to, 0, moved);
      this.draggedId = null;
      await this.saveOrder(reordered);
    },

    async moveVehicle(vehicle, delta) {
      if (!this.sortingEnabled) return;
      const reordered = [...this.vehicles];
      const from = reordered.findIndex(item => item.id === vehicle.id);
      const to = from + delta;
      if (to < 0 || to >= reordered.length) return;
      [reordered[from], reordered[to]] = [reordered[to], reordered[from]];
      await this.saveOrder(reordered);
    },

    async saveOrder(reordered) {
      const previous = this.vehicles;
      this.vehicles = reordered;
      try {
        await this.api(`/api/operation_overview/${this.operationId}/vehicles/order`, {
          method: 'PUT', body: JSON.stringify({ vehicle_ids: reordered.map(item => item.id) })
        });
      } catch (error) {
        this.vehicles = previous;
        this.showToast(error.message);
      }
    },

    openSaveTemplate() {
      this.templateName = '';
      this.modalError = '';
      this.saveTemplateOpen = true;
    },

    async saveTemplate(overwrite) {
      this.modalError = '';
      try {
        await this.api('/api/vehicle-templates', {
          method: 'POST', body: JSON.stringify({
            operation_id: this.operationId, name: this.templateName, overwrite
          })
        });
        this.saveTemplateOpen = false;
        this.showToast(overwrite ? 'Vorlage überschrieben' : 'Vorlage gespeichert');
        await this.loadTemplates();
      } catch (error) {
        if (error.status === 409 && !overwrite
            && confirm('Eine Vorlage mit diesem Namen existiert bereits. Überschreiben?')) {
          await this.saveTemplate(true);
          return;
        }
        this.modalError = error.message;
      }
    },

    async openTemplates() {
      await this.loadTemplates();
      this.templatesOpen = true;
    },

    async applyTemplate(template, mode) {
      if (mode === 'replace' && !confirm(
        'Alle vorhandenen Fahrzeuge dieser Lage und ihre Besatzungszuordnungen werden entfernt. Fortfahren?'
      )) return;
      try {
        await this.api(`/api/vehicle-templates/${template.id}/apply`, {
          method: 'POST', body: JSON.stringify({ operation_id: this.operationId, mode })
        });
        this.templatesOpen = false;
        this.showToast(mode === 'replace' ? 'Fahrzeugliste ersetzt' : 'Vorlage hinzugefügt');
        await this.loadVehicles();
      } catch (error) { this.showToast(error.message); }
    },

    async removeTemplate(template) {
      if (!confirm(`Vorlage „${template.name}“ endgültig löschen?`)) return;
      try {
        await this.api(`/api/vehicle-templates/${template.id}`, { method: 'DELETE' });
        this.showToast('Vorlage gelöscht');
        await this.loadTemplates();
      } catch (error) { this.showToast(error.message); }
    },

    closeTopModal() {
      if (this.crewModalOpen) this.crewModalOpen = false;
      else if (this.vehicleModalOpen) this.closeVehicleModal();
      else if (this.saveTemplateOpen) this.saveTemplateOpen = false;
      else if (this.templatesOpen) this.templatesOpen = false;
    },

    showToast(message) {
      this.toast = message;
      clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toast = ''; }, 3200);
    }
  }));
});
