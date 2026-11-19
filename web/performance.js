const button = document.getElementById('run'), state = document.getElementById('state');
const editor = document.getElementById('test-editor');
window.addEventListener('message', event => {
  if (event.origin !== location.origin || event.source !== editor.contentWindow) return;
  if (event.data?.type === 'benchmark-ready') { button.disabled = false; state.textContent = '可以测量'; }
  if (event.data?.type === 'benchmark-result') {
    button.disabled = false; state.textContent = '测量完成';
    document.getElementById('result').textContent = JSON.stringify(event.data.result, null, 2);
    const rows = document.getElementById('rows'); rows.replaceChildren();
    for (const row of event.data.result.rows) {
      const tr = document.createElement('tr');
      for (const key of ['nodes', 'loadMs', 'renderMs', 'selectMs', 'moveMs', 'undoMs', 'frameMs', 'domElements']) {
        const td = document.createElement('td'); td.textContent = Number.isInteger(row[key]) ? row[key] : row[key].toFixed(2); tr.append(td);
      }
      rows.append(tr);
    }
  }
  if (event.data?.type === 'benchmark-error') { button.disabled = false; state.textContent = event.data.error; }
});
button.addEventListener('click', () => {
  button.disabled = true; state.textContent = '正在测量，请保持测试页可见…';
  editor.contentWindow.postMessage({ type: 'benchmark-run' }, location.origin);
});
