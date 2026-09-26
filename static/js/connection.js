// Single shared Socket.IO connection + Alpine store for the "Live verbunden"
// badge in the topbar. Page-specific scripts (e.g. operation_edit.js) reuse
// window.socket instead of opening a second connection.

const socket = io();
window.socket = socket;

document.addEventListener('alpine:init', () => {
  Alpine.store('connection', { online: socket.connected });
  socket.on('connect',    () => Alpine.store('connection').online = true);
  socket.on('disconnect', () => Alpine.store('connection').online = false);
});
