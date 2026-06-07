const socket = io();

document.addEventListener('alpine:init', () => {
  Alpine.store('connection', { online: false });
  socket.on('connect',    () => Alpine.store('connection').online = true);
  socket.on('disconnect', () => Alpine.store('connection').online = false);

  Alpine.data('inlineField', (type, entityId, field, operationId) => ({
    editing: false,
    input: '',
    filtered: [],
    selIdx: 0,

    open(currentValue) {
      this.input = currentValue ?? '';
      this.editing = true;
      this.doFilter();
      this.$nextTick(() => this.$refs.inp.focus());
    },

    doFilter() {
      const q = this.input.toLowerCase();
      const opts = this.getOptions(field, type);
      this.filtered = opts
        .filter(s => s && s.toLowerCase().includes(q) && s !== this.input)
        .slice(0, 8);
      this.selIdx = 0;
    },

    tabComplete(e) {
      if (this.filtered.length) {
        e.preventDefault();
        this.input = this.filtered[this.selIdx];
        this.filtered = [];
      }
    },

    save() {
      if (!this.editing) return;
      const val = this.input;
      this.editing = false;
      this.filtered = [];
      this.saveField(type, entityId, field, val, operationId);
    }
  }));

  Alpine.data('inlineDateField', (type, entityId, field, operationId) => ({
    editing: false,
    input: '',

    displayDate(ts) {
      if (!ts) return '—';
      return new Date(ts * 1000).toLocaleDateString('de-DE');
    },

    open(ts) {
      if (ts) {
        const d = new Date(ts * 1000);
        this.input = [
          d.getFullYear(),
          String(d.getMonth() + 1).padStart(2, '0'),
          String(d.getDate()).padStart(2, '0')
        ].join('-');
      } else {
        this.input = '';
      }
      this.editing = true;
      this.$nextTick(() => {
        this.$refs.inp.value = this.input;
        this.$refs.inp.focus();
        try { this.$refs.inp.showPicker(); } catch (_) {}
      });
    },

    save() {
      if (!this.editing) return;
      this.editing = false;
      if (!this.input) return;
      const d = new Date(this.input + 'T00:00:00');
      if (isNaN(d)) return;
      this.saveField(type, entityId, field, Math.floor(d.getTime() / 1000), operationId);
    }
  }));

  Alpine.data('editPage', (operation = []) => ({
    operation_id: operation.id,
    operation_name: operation.name,
    operation_place: operation.place,
    operation_date: new Date(operation.date * 1000).toLocaleDateString('de-DE'),
    search: '',

    current_missions: Array.from(operation.missions).filter(m => m.status == 0 || m.status == 1),
    finished_missions: Array.from(operation.missions).filter(m => m.status == 2).sort((a, b) => (b.changed_at || 0) - (a.changed_at || 0)),
    activeMissionId: null,

    getOptions(field, type) {
      const allMissions = [...this.current_missions, ...this.finished_missions];
      if (type === 'mission') {
        return [...new Set(allMissions.map(m => m[field]).filter(Boolean))];
      }
      const allPersons = allMissions.flatMap(m => m.persons || []);
      return [...new Set(allPersons.map(p => p[field]).filter(Boolean))];
    },

    init() {
      socket.emit('join', { operation_id: operation.id });

      let firstConnect = true;
      socket.on('connect', () => {
        if (!firstConnect) {
          socket.emit('join', { operation_id: this.operation_id });
          fetch(`/api/operation_overview/${this.operation_id}`)
            .then(r => r.json())
            .then(data => {
              const all = data.missions;
              this.current_missions  = all.filter(m => m.status == 0 || m.status == 1);
              this.finished_missions = all.filter(m => m.status == 2).sort((a, b) => (b.changed_at || 0) - (a.changed_at || 0));
            });
        }
        firstConnect = false;
      });

      socket.on('mission_updated', (updated) => {
        const all = [...this.current_missions, ...this.finished_missions]
          .map(m => m.id === updated.id ? { ...m, ...updated } : m);
        this.current_missions  = all.filter(m => m.status == 0 || m.status == 1);
        this.finished_missions = all.filter(m => m.status == 2).sort((a, b) => (b.changed_at || 0) - (a.changed_at || 0));
      });

      socket.on('person_updated', (updated) => {
        const patch = (list) => list.map(m => ({
          ...m,
          persons: m.persons.map(p => p.id === updated.id ? { ...p, ...updated } : p)
        }));
        this.current_missions  = patch(this.current_missions);
        this.finished_missions = patch(this.finished_missions);
      });

      socket.on('mission_added', (mission) => {
        this.current_missions = [...this.current_missions, mission];
      });

      socket.on('person_added', ({ mission_id, person }) => {
        const patch = (list) => list.map(m =>
          m.id === mission_id ? { ...m, persons: [...m.persons, person] } : m
        );
        this.current_missions  = patch(this.current_missions);
        this.finished_missions = patch(this.finished_missions);
      });

      socket.on('mission_deleted', ({ mission_id }) => {
        this.current_missions  = this.current_missions.filter(m => m.id !== mission_id);
        this.finished_missions = this.finished_missions.filter(m => m.id !== mission_id);
      });

      socket.on('person_deleted', ({ person_id, mission_id }) => {
        const patch = (list) => list.map(m =>
          m.id === mission_id ? { ...m, persons: m.persons.filter(p => p.id !== person_id) } : m
        );
        this.current_missions  = patch(this.current_missions);
        this.finished_missions = patch(this.finished_missions);
      });
    },

    handleKeydown(e) {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;
      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        this.addMission();
      } else if ((e.key === 'p' || e.key === 'P') && this.activeMissionId) {
        e.preventDefault();
        this.addPerson(this.activeMissionId);
      }
    },

    addMission() {
      socket.emit('add_mission', { operation_id: this.operation_id });
    },

    addPerson(missionId) {
      socket.emit('add_person', { mission_id: missionId, operation_id: this.operation_id });
    },

    deleteMission(missionId, missionNumber) {
      if (!confirm(`Einsatz ${missionNumber} wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.`)) return;
      socket.emit('delete_mission', { mission_id: missionId, operation_id: this.operation_id });
    },

    deletePerson(personId, personNumber, missionId) {
      if (!confirm(`Patient ${personNumber} wirklich löschen? Diese Aktion kann nicht rückgängig gemacht werden.`)) return;
      socket.emit('delete_person', { person_id: personId, mission_id: missionId, operation_id: this.operation_id });
    },

    formatDateTime(ts) {
      if (!ts) return '—';
      return new Date(ts * 1000).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    },

    formatTime(ts) {
        if (!ts) return '—';
        return new Date(ts * 1000).toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit' });
    },

    filteredMissions(list) {
      const q = this.search.trim().toLowerCase();
      if (!q) return list;
      return list.filter(m => {
        const missionMatch = [m.number, m.place, m.unit, m.description]
          .some(v => String(v ?? '').toLowerCase().includes(q));
        const personMatch = (m.persons || []).some(p =>
          [p.last_name, p.name, p.gender, p.handover, p.info]
            .some(v => String(v ?? '').toLowerCase().includes(q))
        );
        return missionMatch || personMatch;
      });
    },

    triageBarStyle(persons) {
      if (!persons || !persons.length) return '';
      const colors = { 0: '#6b7280', 1: '#22c55e', 2: '#eab308', 3: '#ef4444' };
      const pct = 100 / persons.length;
      const sep = '#18181b';
      const stops = [];
      persons.forEach((p, i) => {
        const c = colors[p.triage] ?? '#6b7280';
        const start = i * pct;
        const end = (i + 1) * pct;
        if (i > 0) stops.push(`${sep} ${start}% calc(${start}% + 2px)`);
        stops.push(`${c} ${i > 0 ? `calc(${start}% + 2px)` : `${start}%`} ${end}%`);
      });
      return `background: linear-gradient(to bottom, ${stops.join(', ')})`;
    },

    saveField(type, id, field, value, operationId) {
      socket.emit(`update_${type}`, { [`${type}_id`]: id, field, value, operation_id: operationId });
    }
  }));
});
