const helperSocket = window.socket;

const HELPER_FIELDS = [
  'last_name', 'first_name', 'birth_date', 'gender', 'postal_code', 'city',
  'nationality', 'street', 'mobile', 'email', 'nutrition_type', 'nutrition_note',
  'district_association', 'community', 'deployment_location', 'deployment_info',
  'deployment_start', 'deployment_end', 'membership_number',
  'district_association_raw', 'card_number', 'verification_code', 'qualifications'
];

const QUALIFICATION_OPTIONS = [
  { label: 'Zugführer', short: 'ZF' },
  { label: 'Einsatzleiter', short: 'EL' },
  { label: 'Truppführer', short: 'TF' },
  { label: 'Wasserretter', short: 'WR' },
  { label: 'Taucher', short: 'Taucher' },
  { label: 'Fließwasserretter', short: 'Fließ-WR' },
  { label: 'Rettungsschwimmer im Wasserrettungsdienst', short: 'RS-WRD' },
  { label: 'Sanitäter', short: 'SAN' },
  { label: 'Sanitär mit Fachdienstausbidlung', short: 'SanFD' },
  { label: 'Rettungssanitäter', short: 'RS' },
  { label: 'Notfallsanitäter', short: 'NotSan' },
  { label: 'Arzt', short: 'Arzt' }
];

function blankHelper() {
  const helper = Object.fromEntries(HELPER_FIELDS.map(field => [field, '']));
  const now = new Date();
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
  helper.deployment_start = now.toISOString().slice(0, 16);
  helper.qualifications = [];
  return helper;
}

document.addEventListener('alpine:init', () => {
  Alpine.data('helpersPage', operationId => ({
    operationId,
    helpers: [],
    vehicles: [],
    stats: {
      total: 0,
      status: { Anwesend: 0, Abgemeldet: 0 },
      gender: { m: 0, w: 0, d: 0, none: 0 },
      nutrition: {}
    },
    nutritionOptions: [
      'ohne Einschränkung', 'vegetarisch', 'vegan',
      'Fruktoseintoleranz', 'Laktoseintoleranz', 'Sonstiges'
    ],
    qualificationOptions: QUALIFICATION_OPTIONS,
    filters: { q: '', vehicle: '', qualification: '', nutrition: '', status: '' },
    helperLoadRequest: 0,
    loading: false,
    modalOpen: false,
    tab: 'scan',
    editingId: null,
    form: blankHelper(),
    preview: null,
    rawPayload: null,
    rawSource: null,
    scannerValue: '',
    modalError: '',
    saving: false,
    toast: '',
    toastTimer: null,
    actionMenuHelper: null,
    actionMenuStyle: '',
    qualificationEditorId: null,
    exportMenuOpen: false,
    assignmentModalOpen: false,
    assignmentHelper: null,
    assignmentForm: { vehicle_id: '', role: 'member' },
    assignmentError: '',
    assignmentSaving: false,
    codeReader: null,
    cameraControls: null,
    cameraReleasePromise: null,
    cameraSession: 0,
    cameraStarting: false,
    cameraRunning: false,
    cameras: [],
    selectedCamera: '',
    overlayPoints: '',
    scanLocked: false,

    async init() {
      try { window.ZXingBrowser?.BrowserCodeReader?.releaseAllStreams(); } catch (_) {}
      this.pageHideHandler = () => this.stopCamera();
      this.visibilityHandler = () => { if (document.hidden) this.stopCamera(); };
      this.actionMenuViewportHandler = () => this.closeActionMenu();
      window.addEventListener('pagehide', this.pageHideHandler);
      window.addEventListener('resize', this.actionMenuViewportHandler);
      window.addEventListener('scroll', this.actionMenuViewportHandler, true);
      document.addEventListener('visibilitychange', this.visibilityHandler);
      await Promise.all([this.loadHelpers(), this.loadVehicles()]);
      if (helperSocket) {
        helperSocket.emit('join', { operation_id: this.operationId });
        helperSocket.on('helper_saved', event => {
          if (event.operation_id === this.operationId) this.loadHelpers();
        });
        helperSocket.on('helper_deleted', event => {
          if (event.operation_id === this.operationId) this.loadHelpers();
        });
        helperSocket.on('vehicles_changed', event => {
          if (event.operation_id === this.operationId) {
            this.loadHelpers();
            this.loadVehicles();
          }
        });
      }
    },

    destroy() {
      window.removeEventListener('pagehide', this.pageHideHandler);
      window.removeEventListener('resize', this.actionMenuViewportHandler);
      window.removeEventListener('scroll', this.actionMenuViewportHandler, true);
      document.removeEventListener('visibilitychange', this.visibilityHandler);
      this.stopCamera();
      document.body.style.overflow = '';
    },

    get intoleranceCount() {
      return (this.stats.nutrition.Fruktoseintoleranz || 0)
        + (this.stats.nutrition.Laktoseintoleranz || 0)
        + (this.stats.nutrition.Sonstiges || 0);
    },

    get cameraSupported() {
      return Boolean(window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.ZXingBrowser);
    },

    get cameraHint() {
      if (!window.isSecureContext) return 'Live-Kamera benötigt im WLAN eine vertrauenswürdige HTTPS-Verbindung. Der Bildimport funktioniert weiterhin.';
      if (!navigator.mediaDevices) return 'Dieser Browser stellt keinen Kamerazugriff bereit. Bitte Bildimport oder Scanner verwenden.';
      if (!window.ZXingBrowser) return 'Der lokale QR-Decoder konnte nicht geladen werden.';
      return '';
    },

    async api(url, options = {}) {
      const response = await fetch(url, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options.headers || {}) }
      });
      if (!response.ok) {
        let message = `Fehler ${response.status}`;
        try { message = (await response.json()).error || message; } catch (_) {}
        throw new Error(message);
      }
      if (response.status === 204) return null;
      return response.json();
    },

    async loadHelpers() {
      const requestId = ++this.helperLoadRequest;
      this.loading = true;
      const params = new URLSearchParams(this.filters);
      try {
        const result = await this.api(`/api/operation_overview/${this.operationId}/helpers?${params}`);
        if (requestId !== this.helperLoadRequest) return;
        this.helpers = result.items;
        this.stats = result.stats;
      } catch (error) {
        if (requestId === this.helperLoadRequest) this.showToast(error.message);
      } finally {
        if (requestId === this.helperLoadRequest) this.loading = false;
      }
    },

    searchHelpers(value) {
      this.filters.q = value;
      this.loadHelpers();
    },

    async loadVehicles() {
      try {
        const result = await this.api(`/api/operation_overview/${this.operationId}/vehicles`);
        this.vehicles = result.items;
      } catch (error) {
        this.showToast(error.message);
      }
    },

    openAssignmentModal(helper) {
      if (helper.status !== 'Anwesend') return;
      this.assignmentHelper = helper;
      this.assignmentForm = {
        vehicle_id: helper.vehicle_id || '',
        role: helper.vehicle_role || 'member'
      };
      this.assignmentError = '';
      this.assignmentModalOpen = true;
    },

    closeAssignmentModal() {
      this.assignmentModalOpen = false;
      this.assignmentHelper = null;
      this.assignmentError = '';
    },

    async saveAssignment() {
      if (!this.assignmentHelper || this.assignmentSaving) return;
      const vehicleId = this.assignmentForm.vehicle_id ? Number(this.assignmentForm.vehicle_id) : null;
      if (this.assignmentHelper.vehicle_id && vehicleId
          && vehicleId !== this.assignmentHelper.vehicle_id
          && !confirm('Die Person ist bereits einem Fahrzeug zugeordnet. In das ausgewählte Fahrzeug verschieben?')) return;
      this.assignmentSaving = true;
      this.assignmentError = '';
      try {
        await this.api(`/api/operation_overview/${this.operationId}/vehicle-assignments/${this.assignmentHelper.id}`, {
          method: 'PUT',
          body: JSON.stringify({ vehicle_id: vehicleId, role: vehicleId ? this.assignmentForm.role : 'member' })
        });
        this.closeAssignmentModal();
        this.showToast(vehicleId ? 'Fahrzeugzuordnung gespeichert' : 'Fahrzeugzuordnung entfernt');
        await Promise.all([this.loadHelpers(), this.loadVehicles()]);
      } catch (error) {
        this.assignmentError = error.message;
      } finally {
        this.assignmentSaving = false;
      }
    },

    toggleActionMenu(event, helper) {
      if (this.actionMenuHelper?.id === helper.id) {
        this.closeActionMenu();
        return;
      }
      const rect = event.currentTarget.getBoundingClientRect();
      const width = 180;
      const height = 126;
      const gutter = 8;
      const left = Math.max(gutter, Math.min(window.innerWidth - width - gutter, rect.right - width));
      const top = rect.bottom + height + gutter <= window.innerHeight
        ? rect.bottom + 5
        : Math.max(gutter, rect.top - height - 5);
      this.actionMenuStyle = `position:fixed;left:${Math.round(left)}px;top:${Math.round(top)}px;width:${width}px;`;
      this.actionMenuHelper = helper;
    },

    closeActionMenu() {
      this.actionMenuHelper = null;
      this.actionMenuStyle = '';
    },

    toggleQualificationEditor(helper) {
      this.qualificationEditorId = this.qualificationEditorId === helper.id ? null : helper.id;
    },

    closeQualificationEditor() {
      this.qualificationEditorId = null;
    },

    openModal() {
      this.closeActionMenu();
      this.resetModal();
      this.modalOpen = true;
      document.body.style.overflow = 'hidden';
      this.$nextTick(() => this.$refs.scannerInput?.focus());
    },

    resetModal() {
      this.stopCamera();
      this.tab = 'scan';
      this.editingId = null;
      this.form = blankHelper();
      this.preview = null;
      this.rawPayload = null;
      this.rawSource = null;
      this.scannerValue = '';
      this.modalError = '';
      this.saving = false;
      this.scanLocked = false;
    },

    closeModal() {
      this.stopCamera();
      this.modalOpen = false;
      document.body.style.overflow = '';
      this.preview = null;
      this.rawPayload = null;
    },

    switchTab(tab) {
      this.tab = tab;
      this.modalError = '';
      if (tab !== 'scan') this.stopCamera();
      if (tab === 'scan') this.$nextTick(() => this.$refs.scannerInput?.focus());
    },

    async submitScanner() {
      const raw = this.scannerValue.trim();
      if (!raw) return;
      await this.processRawPayload(raw);
    },

    async processRawPayload(raw, lockAlreadyHeld = false) {
      if (this.scanLocked && !lockAlreadyHeld) return;
      this.scanLocked = true;
      this.modalError = '';
      try {
        const result = await this.api(`/api/operation_overview/${this.operationId}/helpers/preview`, {
          method: 'POST',
          body: JSON.stringify({ raw_payload: raw })
        });
        this.rawPayload = raw;
        this.rawSource = result.source;
        const blank = blankHelper();
        this.form = { ...blank, ...result.data, deployment_start: blank.deployment_start };
        this.preview = result;
        this.scannerValue = '';
        await this.stopCamera(false);
      } catch (error) {
        this.modalError = error.message;
        this.scanLocked = false;
        this.$nextTick(() => this.$refs.scannerInput?.focus());
      }
    },

    editablePayload() {
      return Object.fromEntries(HELPER_FIELDS.map(field => [field, this.form[field] || null]));
    },

    async saveHelper() {
      if (this.saving) return;
      if (!this.form.last_name || !this.form.first_name || !this.form.birth_date) {
        this.modalError = 'Nachname, Vorname und Geburtsdatum sind Pflichtfelder.';
        return;
      }
      this.saving = true;
      this.modalError = '';
      try {
        let result;
        if (this.editingId) {
          const payload = { ...this.editablePayload(), status: this.form.status };
          result = await this.api(`/api/operation_overview/${this.operationId}/helpers/${this.editingId}`, {
            method: 'PATCH', body: JSON.stringify(payload)
          });
          this.showToast('Änderungen gespeichert');
        } else {
          result = await this.api(`/api/operation_overview/${this.operationId}/helpers`, {
            method: 'POST',
            body: JSON.stringify({ data: this.editablePayload(), raw_payload: this.rawPayload })
          });
          this.showToast(result.message);
        }
        this.closeModal();
        await this.loadHelpers();
      } catch (error) {
        this.modalError = error.message;
      } finally {
        this.saving = false;
      }
    },

    editHelper(helper) {
      this.resetModal();
      this.editingId = helper.id;
      this.tab = 'manual';
      this.form = { ...blankHelper(), ...helper };
      this.rawSource = helper.sources?.includes('DRK-Server-QR') ? 'DRK-Server-QR' : null;
      this.modalOpen = true;
    },

    async toggleStatus(helper) {
      const status = helper.status === 'Anwesend' ? 'Abgemeldet' : 'Anwesend';
      try {
        await this.api(`/api/operation_overview/${this.operationId}/helpers/${helper.id}`, {
          method: 'PATCH', body: JSON.stringify({ status })
        });
        this.showToast(`Status auf „${status}“ gesetzt`);
        await this.loadHelpers();
      } catch (error) { this.showToast(error.message); }
    },

    async updateField(helper, field, value) {
      const normalizedValue = value === '' ? null : value;
      const currentValue = helper[field] ?? null;
      if (normalizedValue === currentValue) return;
      try {
        const updated = await this.api(`/api/operation_overview/${this.operationId}/helpers/${helper.id}`, {
          method: 'PATCH', body: JSON.stringify({ [field]: normalizedValue })
        });
        Object.assign(helper, updated);
        this.showToast('Änderung gespeichert');
      } catch (error) {
        this.showToast(error.message);
        await this.loadHelpers();
      }
    },

    hasQualification(helper, qualification) {
      return Boolean(helper?.qualifications?.includes(qualification));
    },

    toggleFormQualification(qualification) {
      const selected = new Set(this.form.qualifications || []);
      selected.has(qualification) ? selected.delete(qualification) : selected.add(qualification);
      this.form.qualifications = this.qualificationOptions
        .map(option => option.short)
        .filter(value => selected.has(value));
    },

    async toggleQualification(helper, qualification) {
      const selected = new Set(helper.qualifications || []);
      selected.has(qualification) ? selected.delete(qualification) : selected.add(qualification);
      const qualifications = this.qualificationOptions
        .map(option => option.short)
        .filter(value => selected.has(value));
      try {
        const updated = await this.api(`/api/operation_overview/${this.operationId}/helpers/${helper.id}`, {
          method: 'PATCH', body: JSON.stringify({ qualifications })
        });
        Object.assign(helper, updated);
        if (this.qualificationEditorId === helper.id
            && helper.qualifications.length === this.qualificationOptions.length) {
          this.closeQualificationEditor();
        }
        this.showToast('Qualifikationen gespeichert');
      } catch (error) {
        this.showToast(error.message);
        await this.loadHelpers();
      }
    },

    qualificationRowClass(helper) {
      if (this.hasQualification(helper, 'ZF')) return 'helper-row--zugfuehrer';
      if (this.hasQualification(helper, 'EL')) return 'helper-row--einsatzleiter';
      if (helper.vehicle_role === 'leader') return 'helper-row--gruppenfuehrer';
      return '';
    },

    async removeHelper(helper) {
      if (!confirm(`${helper.first_name} ${helper.last_name} endgültig löschen?`)) return;
      try {
        await this.api(`/api/operation_overview/${this.operationId}/helpers/${helper.id}`, { method: 'DELETE' });
        this.showToast('Helfer gelöscht');
        await this.loadHelpers();
      } catch (error) { this.showToast(error.message); }
    },

    async startCamera() {
      if (!this.cameraSupported || this.cameraRunning || this.cameraStarting) return;
      this.cameraStarting = true;
      this.modalError = '';
      this.overlayPoints = '';
      this.scanLocked = false;
      await this.stopCamera();

      let lastError = null;
      const candidates = this.selectedCamera ? [this.selectedCamera, undefined] : [undefined, undefined];
      for (let attempt = 0; attempt < candidates.length; attempt += 1) {
        const deviceId = candidates[attempt];
        const session = ++this.cameraSession;
        try {
          this.codeReader = new ZXingBrowser.BrowserQRCodeReader();
          this.cameraRunning = true;
          const controls = await this.codeReader.decodeFromVideoDevice(
            deviceId, this.$refs.cameraVideo,
            (result, error, callbackControls) => {
              if (!result || this.scanLocked || session !== this.cameraSession) return;
              this.drawDetection(result);
              this.cameraControls = callbackControls;
              this.handleCameraResult(result.getText());
            }
          );
          if (session !== this.cameraSession) {
            await Promise.resolve(controls.stop());
            this.cameraStarting = false;
            return;
          }
          this.cameraControls = controls;
          const devices = await ZXingBrowser.BrowserCodeReader.listVideoInputDevices();
          this.cameras = devices.slice(0, 5);
          if (!this.selectedCamera && this.cameras.length) {
            const rear = this.cameras.find(device => /back|rear|environment|rück/i.test(device.label));
            this.selectedCamera = (rear || this.cameras[0]).deviceId;
          }
          this.cameraStarting = false;
          return;
        } catch (error) {
          lastError = error;
          await this.stopCamera();
          const recoverable = error?.name === 'NotReadableError'
            || /could not start video source|track start/i.test(error?.message || '');
          if (!recoverable || attempt === candidates.length - 1) break;
          this.selectedCamera = '';
          await new Promise(resolve => setTimeout(resolve, 350));
        }
      }

      this.cameraStarting = false;
      this.modalError = lastError?.name === 'NotAllowedError'
          ? 'Kamerazugriff wurde nicht erlaubt. Bitte Berechtigung erteilen oder ein Bild laden.'
          : (lastError?.name === 'NotReadableError' || /could not start video source/i.test(lastError?.message || ''))
            ? 'Die Kamera ist noch belegt oder wird von einer anderen App verwendet. Bitte kurz warten und erneut versuchen.'
            : `Kamera konnte nicht gestartet werden: ${lastError?.message || lastError}`;
    },

    async handleCameraResult(raw) {
      if (this.scanLocked) return;
      this.scanLocked = true;
      await this.stopCamera(false);
      await this.processRawPayload(raw, true);
    },

    async stopCamera(clearOverlay = true) {
      const controls = this.cameraControls;
      const video = this.$refs?.cameraVideo;
      const stream = video?.srcObject;
      this.cameraControls = null;
      this.codeReader = null;
      this.cameraSession += 1;
      this.cameraRunning = false;
      if (clearOverlay) this.overlayPoints = '';

      const previousRelease = this.cameraReleasePromise || Promise.resolve();
      const releaseTask = previousRelease.catch(() => {}).then(async () => {
        try { await Promise.resolve(controls?.stop()); } catch (_) {}
        try { stream?.getTracks().forEach(track => track.stop()); } catch (_) {}
        try { window.ZXingBrowser?.BrowserCodeReader?.releaseAllStreams(); } catch (_) {}
        if (video) {
          try { video.pause(); } catch (_) {}
          try { window.ZXingBrowser?.BrowserCodeReader?.cleanVideoSource(video); } catch (_) {
            try { video.srcObject = null; } catch (_) { video.src = ''; }
            video.removeAttribute('src');
          }
          try { video.load(); } catch (_) {}
        }
        await new Promise(resolve => setTimeout(resolve, 120));
      });
      this.cameraReleasePromise = releaseTask;
      await releaseTask;
      if (this.cameraReleasePromise === releaseTask) this.cameraReleasePromise = null;
    },

    async restartCamera() {
      await this.stopCamera();
      await this.$nextTick();
      await this.startCamera();
    },

    drawDetection(result) {
      const points = result.getResultPoints?.() || [];
      const video = this.$refs.cameraVideo;
      if (!points.length || !video.videoWidth || !video.videoHeight) return;
      const xs = points.map(point => point.getX());
      const ys = points.map(point => point.getY());
      const scaleX = video.clientWidth / video.videoWidth;
      const scaleY = video.clientHeight / video.videoHeight;
      const left = Math.min(...xs) * scaleX;
      const right = Math.max(...xs) * scaleX;
      const top = Math.min(...ys) * scaleY;
      const bottom = Math.max(...ys) * scaleY;
      this.overlayPoints = `${left},${top} ${right},${top} ${right},${bottom} ${left},${bottom}`;
    },

    async decodeImage(event) {
      const file = event.target.files?.[0];
      if (!file) return;
      this.modalError = '';
      const url = URL.createObjectURL(file);
      try {
        const reader = new ZXingBrowser.BrowserQRCodeReader();
        const result = await reader.decodeFromImageUrl(url);
        await this.processRawPayload(result.getText());
      } catch (error) {
        this.modalError = 'In der Bilddatei konnte kein lesbarer QR-Code gefunden werden.';
      } finally {
        URL.revokeObjectURL(url);
        event.target.value = '';
      }
    },

    isConflict(field) {
      return Boolean(this.preview?.conflicts?.some(conflict => conflict.field === field));
    },

    genderLabel(value) {
      return ({ m: 'Männlich', w: 'Weiblich', d: 'Divers' })[value] || 'Keine Angabe';
    },

    genderClass(value) {
      return ({ m: 'tag--blue', w: 'tag--pink', d: 'tag--purple' })[value] || 'tag--muted';
    },

    nutritionClass(value) {
      if (value === 'vegetarisch') return 'tag--green';
      if (value === 'vegan') return 'tag--purple';
      if (value === 'ohne Einschränkung') return 'tag--blue';
      if (value) return 'tag--amber';
      return 'tag--muted';
    },

    nutritionLabel(helper) {
      if (!helper?.nutrition_type) return 'Keine Angabe';
      return helper.nutrition_type === 'Sonstiges' && helper.nutrition_note
        ? helper.nutrition_note : helper.nutrition_type;
    },

    formatBirthDate(value) {
      if (!value) return '—';
      const [year, month, day] = value.split('-');
      return `${day}.${month}.${year}`;
    },

    formatRegistered(timestamp) {
      if (!timestamp) return '—';
      return new Date(timestamp * 1000).toLocaleString('de-DE', {
        day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit'
      });
    },

    showToast(message) {
      this.toast = message;
      clearTimeout(this.toastTimer);
      this.toastTimer = setTimeout(() => { this.toast = ''; }, 3500);
    }
  }));
});
