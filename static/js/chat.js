/* Both chat surfaces use the same server-side session conversation. */
(() => {
  const root = document.querySelector('.schedule-chat');
  if (!root) return;
  const dialog = document.querySelector('#schedule-chat-panel');
  const launcher = document.querySelector('[data-chat-open]');
  const form = root.querySelector('form');
  const field = root.querySelector('textarea');
  const log = root.querySelector('.chat-messages');
  const status = root.querySelector('.chat-status');
  let busy = false;
  const render = (messages) => {
    log.replaceChildren();
    if (!messages.length) {
      const empty = document.createElement('p');
      empty.textContent = 'Start with a question. Follow up naturally; schedule answers look up current data.';
      log.append(empty);
    }
    for (const message of messages) {
      const article = document.createElement('article');
      article.className = `chat-message chat-message-${message.role}`;
      const author = document.createElement('strong');
      author.textContent = message.role === 'user' ? 'You' : 'Smart Schedule';
      const body = document.createElement('p');
      body.textContent = message.content;
      article.append(author, body);
      if (message.role === 'assistant') {
        const copy = document.createElement('button');
        copy.type = 'button';
        copy.className = 'btn btn-outline-secondary btn-sm';
        copy.textContent = 'Copy answer';
        copy.addEventListener('click', async () => {
          try {
            await navigator.clipboard.writeText(message.content);
            status.textContent = 'Answer copied.';
          } catch {
            const range = document.createRange();
            range.selectNodeContents(body);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            status.textContent = 'Copy is unavailable. The answer is selected; copy it manually.';
          }
        });
        article.append(copy);
      }
      log.append(article);
    }
    log.scrollTop = log.scrollHeight;
  };
  async function request(method = 'GET', message) {
    if (busy) return;
    busy = true;
    root.setAttribute('aria-busy', 'true');
    root.querySelectorAll('button').forEach(button => { button.disabled = true; });
    status.textContent = method === 'POST' ? 'Checking your schedule…' : 'Loading conversation…';
    try {
      const response = await fetch(root.dataset.chatUrl, {
        method, credentials: 'same-origin',
        headers: {'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name=csrfmiddlewaretoken]').value},
        ...(method === 'POST' ? {body: JSON.stringify({message})} : {})
      });
      let data;
      try { data = await response.json(); } catch { throw new Error('Chat could not load. Refresh the page and sign in again if needed.'); }
      if (!response.ok) throw new Error(data.detail || (data.message || []).join(' ') || 'Chat could not answer. Please try again.');
      render(data.messages);
      status.textContent = '';
      if (method === 'POST') field.value = '';
    } catch (error) {
      status.textContent = error.message || 'Connection failed. Please try again.';
    } finally {
      busy = false;
      root.setAttribute('aria-busy', 'false');
      root.querySelectorAll('button').forEach(button => { button.disabled = false; });
    }
  }
  form.addEventListener('submit', event => {
    event.preventDefault();
    if (field.value.trim()) request('POST', field.value.trim());
  });
  root.querySelector('[data-chat-clear]').addEventListener('click', () => request('DELETE'));
  root.querySelectorAll('[data-chat-example]').forEach(button => {
    button.addEventListener('click', () => { field.value = button.textContent; field.focus(); });
  });
  if (dialog && launcher) {
    launcher.hidden = false;
    launcher.addEventListener('click', () => { dialog.showModal(); request(); field.focus(); });
    dialog.querySelector('[data-chat-close]').addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => launcher.focus());
  } else {
    request();
  }
})();
