// Tela de entrada (versão 2.3): entrar, criar conta e recuperar a senha pela pergunta secreta.
const $ = (selector) => document.querySelector(selector);
const OFFLINE_MESSAGE = 'Sem conexão com o servidor. Verifique se a Agenda Acadêmica está em execução e tente novamente.';

async function send(path, data) {
  let response;
  try {
    response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
  } catch {
    throw new Error(OFFLINE_MESSAGE);
  }
  let body = {};
  try { body = await response.json(); } catch { /* resposta sem JSON */ }
  if (!response.ok) throw new Error(body.error || 'Não foi possível concluir esta ação.');
  return body;
}

function showError(form, message = '') {
  const box = form.querySelector('.form-error');
  box.textContent = message;
  box.hidden = !message;
}

function show(view) {
  document.querySelectorAll('[data-panel]').forEach(panel => { panel.hidden = panel.dataset.panel !== view; });
  document.querySelectorAll('.auth-tab').forEach(tab => {
    const selected = tab.dataset.view === view;
    tab.classList.toggle('active', selected);
    tab.setAttribute('aria-pressed', String(selected));
  });
  if (view === 'recover') resetRecovery();
  document.querySelectorAll('form').forEach(form => showError(form));
  history.replaceState(null, '', view === 'login' ? '/login' : `/login#${view}`);
  $(`[data-panel="${view}"] input`).focus();
}

// Valida, desativa o botão enquanto espera o servidor e mostra o erro dentro do próprio formulário.
function handle(form, action) {
  form.addEventListener('submit', async event => {
    event.preventDefault();
    showError(form);
    if (!form.reportValidity()) return;
    const button = form.querySelector('[type="submit"]');
    button.disabled = true;
    try {
      await action();
    } catch (error) {
      showError(form, error.message);
    } finally {
      button.disabled = false;
    }
  });
}

function sameValue(first, second) {
  if ($(first).value === $(second).value) return true;
  $(second).focus();
  throw new Error('As senhas digitadas não são iguais.');
}

handle($('#login-form'), async () => {
  await send('/api/login', { username: $('#login-username').value, password: $('#login-password').value });
  window.location.href = '/';
});

handle($('#register-form'), async () => {
  sameValue('#register-password', '#register-confirm');
  await send('/api/register', {
    name: $('#register-name').value,
    username: $('#register-username').value,
    password: $('#register-password').value,
    question: $('#register-question').value,
    answer: $('#register-answer').value,
  });
  window.location.href = '/';
});

// Recuperação em duas etapas: 1) usuário -> mostra a pergunta; 2) resposta + nova senha.
const recovery = { step: 1 };

function resetRecovery() {
  recovery.step = 1;
  $('#recover-form').reset();
  $('#recover-username').readOnly = false;
  $('#recover-step-2').hidden = true;
  $('#recover-step-2').disabled = true;
  $('#recover-text').textContent = 'Informe o seu usuário para ver a sua pergunta secreta.';
  $('#recover-submit').textContent = 'Continuar';
}

handle($('#recover-form'), async () => {
  const username = $('#recover-username').value;
  if (recovery.step === 1) {
    const { question } = await send('/api/password/question', { username });
    recovery.step = 2;
    $('#recover-username').readOnly = true;
    $('#recover-question').textContent = question;
    $('#recover-step-2').disabled = false;
    $('#recover-step-2').hidden = false;
    $('#recover-text').textContent = 'Responda à sua pergunta secreta e escolha uma nova senha.';
    $('#recover-submit').textContent = 'Salvar nova senha';
    $('#recover-answer').focus();
    return;
  }
  sameValue('#recover-password', '#recover-confirm');
  await send('/api/password/reset', { username, answer: $('#recover-answer').value, new_password: $('#recover-password').value });
  window.location.href = '/';
});

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => show(button.dataset.view)));
const initial = window.location.hash.slice(1);
show(['register', 'recover'].includes(initial) ? initial : 'login');
