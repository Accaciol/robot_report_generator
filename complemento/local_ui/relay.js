(() => {
  const origin = __LOCAL_ORIGIN__, button = document.getElementById('ruzy-prepare');
  if (!button || document.getElementById('ruzy-final-result')) return;
  let last = 0;
  window.addEventListener('message', event => {
    if (event.source !== parent || event.origin !== origin || event.data?.type !== 'RUZY_AVAILABLE') return;
    last = Date.now(); button.disabled = !event.data.available;
    button.style.background = button.disabled ? '#aaa' : '#17644c';
  });
  button.onclick = event => { if (event.isTrusted && !button.disabled) parent.postMessage({type: 'RUZY_CONFIGURE'}, origin); };
  setInterval(() => { if (Date.now() - last > 5000) { button.disabled = true; button.style.background = '#aaa'; } }, 1000);
})();
