// Alpine component for the main page.
// Registered via the alpine:init event -> works regardless of when Alpine
// starts (see script order in base.html).

window.addEventListener('pageshow', (e) => {
  if (e.persisted) window.location.reload();
});

document.addEventListener('alpine:init', () => {
  Alpine.data('selectionPage', (operations = []) => ({
    newName: '',

    rows: Array.from({ length: Math.max(operations.length, 9) }, (_, i) => {
      console.log(operations);
      const s = operations[i];
      if (!s) return null;
      return {
        ...s,
        date: s.date ? new Date(s.date * 1000).toLocaleDateString('de-DE') : '',
      };
    }),

    async createoperation() {
      if (!this.newName.trim()) return;
      const r = await fetch("/api/operation_overview", {
        method: 'POST',
        headers: { 'Content-Type': 'application/json'},
        body: JSON.stringify({"name": this.newName}),
      });
      if(r.ok){
        const operation = await r.json();
        window.location.href = '/operation_overview/' + operation.id;
      }
    },
  }));
});