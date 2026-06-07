const socket = io();

document.addEventListener('alpine:init', () => {

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

    current_missions: Array.from(operation.missions).filter(m => m.status == 0 || m.status == 1),
    finished_missions: Array.from(operation.missions).filter(m => m.status == 2).sort((a, b) => (b.changed_at || 0) - (a.changed_at || 0)),

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
    },

    addMission() {
      socket.emit('add_mission', { operation_id: this.operation_id });
    },

    addPerson(missionId) {
      socket.emit('add_person', { mission_id: missionId, operation_id: this.operation_id });
    },

    formatDateTime(ts) {
      if (!ts) return '—';
      return new Date(ts * 1000).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    },

    formatTime(ts) {
        if (!ts) return '—';
        return new Date(ts * 1000).toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit' });
    },

    saveField(type, id, field, value, operationId) {
      socket.emit(`update_${type}`, { [`${type}_id`]: id, field, value, operation_id: operationId });
    }
  }));
});
