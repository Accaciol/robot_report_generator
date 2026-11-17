'use strict';
const form = document.getElementById('decision');
let busy = false;
async function decide(status) {
  if (busy) return;
  busy = true; form.querySelectorAll('button').forEach(button => button.disabled = true);
  try {
    const response = await fetch('/decision', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({candidate_id: form.dataset.candidate, attempt: form.dataset.attempt, status, title: document.getElementById('title').value, description: document.getElementById('description').value})});
    const value = await response.json();
    if (!response.ok) throw Error(value.error);
    document.getElementById('form-status').textContent = 'Decisão registrada. Consulte o relatório para exportar o resultado.';
    form.hidden = true;
  } catch (e) { busy = false; document.getElementById('form-status').textContent = e.message; form.querySelectorAll('button').forEach(button => button.disabled = false); }
}
form.onsubmit = event => { event.preventDefault(); decide('saved'); };
document.getElementById('discard').onclick = () => { if (confirm('Descartar este candidato e continuar?')) decide('discarded'); };
