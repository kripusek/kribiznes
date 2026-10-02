// Prevent accidental repeated submits; transactions and revisions enforce correctness.
// Restore controls when returning from an error page through the browser's back cache.
window.addEventListener('pageshow', () => {
 document.querySelectorAll('form[data-sending]').forEach(form => delete form.dataset.sending);
 document.querySelectorAll('button[data-submit-lock]').forEach(button => {
  button.disabled = false;
  delete button.dataset.submitLock;
 });
});
document.addEventListener('submit', event => {
 const form = event.target;
 if (form.dataset.sending === 'yes') { event.preventDefault(); return; }
 form.dataset.sending = 'yes';
 setTimeout(() => form.querySelectorAll('button:not(:disabled)').forEach(button => {
  button.dataset.submitLock = 'yes';
  button.disabled = true;
 }), 0);
});
