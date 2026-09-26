document.addEventListener('alpine:init', () => {
  Alpine.data('accountMenu', (initialRole = 'guest') => ({
    role: initialRole,
    menuOpen: false,
    passwordOpen: false,
    password: '',
    error: '',
    busy: false,

    closeAll() {
      this.menuOpen = false;
      this.closePassword();
    },

    closePassword() {
      this.passwordOpen = false;
      this.password = '';
      this.error = '';
    },

    chooseAdmin() {
      this.menuOpen = false;
      if (this.role === 'admin') return;
      this.passwordOpen = true;
      this.$nextTick(() => this.$refs.adminPassword?.focus());
    },

    async chooseGuest() {
      this.menuOpen = false;
      if (this.role === 'guest' || this.busy) return;
      this.busy = true;
      try {
        const response = await fetch('/api/auth/guest', { method: 'POST' });
        if (!response.ok) throw new Error('Account konnte nicht gewechselt werden.');
        window.location.reload();
      } catch (error) {
        window.alert(error.message);
        this.busy = false;
      }
    },

    async submitAdmin() {
      if (!this.password || this.busy) return;
      this.busy = true;
      this.error = '';
      try {
        const response = await fetch('/api/auth/admin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ password: this.password }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          this.error = payload.error || 'Admin-Anmeldung fehlgeschlagen.';
          return;
        }
        window.location.reload();
      } catch (_) {
        this.error = 'Der Server ist momentan nicht erreichbar.';
      } finally {
        this.busy = false;
      }
    },
  }));

  Alpine.data('passwordSettings', (initialDefaultPassword = false) => ({
    defaultPassword: initialDefaultPassword,
    currentPassword: '',
    newPassword: '',
    confirmation: '',
    error: '',
    success: '',
    busy: false,

    async submit() {
      if (this.busy) return;
      this.busy = true;
      this.error = '';
      this.success = '';
      try {
        const response = await fetch('/api/settings/admin-password', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            current_password: this.currentPassword,
            new_password: this.newPassword,
            confirmation: this.confirmation,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          this.error = payload.error || 'Das Passwort konnte nicht geändert werden.';
          return;
        }
        this.currentPassword = '';
        this.newPassword = '';
        this.confirmation = '';
        this.defaultPassword = false;
        this.success = payload.message;
      } catch (_) {
        this.error = 'Der Server ist momentan nicht erreichbar.';
      } finally {
        this.busy = false;
      }
    },
  }));
});
