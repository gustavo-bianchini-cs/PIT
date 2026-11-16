const state = { tasks: [], filter: 'all', editingId: null };
const $ = (selector) => document.querySelector(selector);
const taskList = $('#task-list');
const dialog = $('#task-dialog');
const form = $('#task-form');
const toast = $('#toast');
let toastTimer;

function notice(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3500);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  let body;
  try { body = await response.json(); } catch { throw new Error('Não foi possível ler a resposta do servidor.'); }
  if (!response.ok) throw new Error(body.error || 'Não foi possível concluir esta ação.');
  return body;
}

function formatDate(value) {
  const [year, month, day] = value.split('-').map(Number);
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(year, month - 1, day));
}

function isOverdue(task) {
  const now = new Date();
  const localToday = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
  return !task.completed && task.due_date < localToday;
}

function makeButton(label, action, icon, className = '') {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `icon-button ${className}`;
  button.setAttribute('aria-label', label);
  button.dataset.action = action;
  button.textContent = icon;
  return button;
}

function render() {
  const tasks = state.tasks;
  $('#total-count').textContent = tasks.length;
  $('#pending-count').textContent = tasks.filter(t => !t.completed).length;
  $('#completed-count').textContent = tasks.filter(t => t.completed).length;
  const visible = tasks.filter(t => state.filter === 'all' || (state.filter === 'completed' ? t.completed : !t.completed));
  taskList.replaceChildren();
  if (visible.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    const illustration = document.createElement('div');
    illustration.className = 'empty-illustration';
    illustration.setAttribute('aria-hidden', 'true');
    illustration.textContent = '✎';
    const heading = document.createElement('h3');
    heading.textContent = tasks.length === 0 ? 'Sua agenda começa aqui' : 'Nenhuma tarefa nesta lista';
    const message = document.createElement('p');
    message.textContent = tasks.length === 0 ? 'Adicione sua primeira tarefa para organizar seus próximos prazos.' : 'Escolha outro filtro para ver suas tarefas.';
    empty.append(illustration, heading, message);
    taskList.append(empty);
    return;
  }
  for (const task of visible) {
    const row = document.createElement('article');
    row.className = `task-row${task.completed ? ' completed' : ''}`;
    row.dataset.id = task.id;
    const check = document.createElement('button');
    check.type = 'button';
    check.className = 'check-button';
    check.dataset.action = 'toggle';
    check.setAttribute('aria-label', task.completed ? `Reabrir ${task.title}` : `Concluir ${task.title}`);
    check.setAttribute('aria-pressed', String(task.completed));
    check.textContent = task.completed ? '✓' : '';
    const body = document.createElement('div');
    body.className = 'task-body';
    const title = document.createElement('h3');
    title.textContent = task.title;
    const meta = document.createElement('div');
    meta.className = 'task-meta';
    const subject = document.createElement('span');
    subject.className = 'subject-pill';
    subject.textContent = task.subject;
    const due = document.createElement('span');
    due.className = `due-date${isOverdue(task) ? ' overdue' : ''}`;
    due.textContent = task.completed ? 'Concluída' : `${isOverdue(task) ? 'Atrasada · ' : 'Entrega · '}${formatDate(task.due_date)}`;
    meta.append(subject, due);
    body.append(title, meta);
    if (task.notes) {
      const notes = document.createElement('p');
      notes.className = 'task-notes';
      notes.textContent = task.notes;
      body.append(notes);
    }
    const actions = document.createElement('div');
    actions.className = 'task-actions';
    actions.append(makeButton(`Editar ${task.title}`, 'edit', '✎'), makeButton(`Excluir ${task.title}`, 'delete', '×', 'delete-button'));
    row.append(check, body, actions);
    taskList.append(row);
  }
}

async function refresh() {
  const body = await api('/api/tasks');
  state.tasks = body.tasks;
  render();
}

function openForm(task = null) {
  state.editingId = task?.id ?? null;
  $('#form-title').textContent = task ? 'Editar tarefa' : 'Nova tarefa';
  $('#save-task').textContent = task ? 'Salvar alterações' : 'Salvar tarefa';
  form.reset();
  if (task) {
    $('#title').value = task.title;
    $('#subject').value = task.subject;
    $('#due-date').value = task.due_date;
    $('#notes').value = task.notes;
  }
  dialog.showModal();
  $('#title').focus();
}

function closeForm() { dialog.close(); state.editingId = null; }

$('#new-task').addEventListener('click', () => openForm());
$('#close-dialog').addEventListener('click', closeForm);
$('#cancel-dialog').addEventListener('click', closeForm);
dialog.addEventListener('click', event => { if (event.target === dialog) closeForm(); });
dialog.addEventListener('close', () => { state.editingId = null; });

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const submit = $('#save-task');
  submit.disabled = true;
  const existing = state.tasks.find(t => t.id === state.editingId);
  const payload = {
    title: $('#title').value.trim(), subject: $('#subject').value.trim(),
    due_date: $('#due-date').value, notes: $('#notes').value.trim(),
    completed: existing?.completed ?? false,
  };
  try {
    await api(state.editingId ? `/api/tasks/${state.editingId}` : '/api/tasks', {
      method: state.editingId ? 'PUT' : 'POST', body: JSON.stringify(payload),
    });
    closeForm();
    await refresh();
    notice(existing ? 'Tarefa atualizada.' : 'Tarefa criada.');
  } catch (error) { notice(error.message, true); }
  finally { submit.disabled = false; }
});

taskList.addEventListener('click', async event => {
  const button = event.target.closest('button[data-action]');
  const row = button?.closest('[data-id]');
  if (!row) return;
  const task = state.tasks.find(t => t.id === Number(row.dataset.id));
  if (!task) return;
  if (button.dataset.action === 'edit') { openForm(task); return; }
  if (button.dataset.action === 'delete' && !confirm(`Excluir a tarefa “${task.title}”?`)) return;
  button.disabled = true;
  try {
    if (button.dataset.action === 'delete') {
      await api(`/api/tasks/${task.id}`, { method: 'DELETE' });
      notice('Tarefa excluída.');
    } else {
      await api(`/api/tasks/${task.id}`, {
        method: 'PUT', body: JSON.stringify({ ...task, completed: !task.completed }),
      });
      notice(task.completed ? 'Tarefa reaberta.' : 'Tarefa concluída.');
    }
    await refresh();
  } catch (error) { notice(error.message, true); button.disabled = false; }
});

document.querySelectorAll('.filter').forEach(button => button.addEventListener('click', () => {
  state.filter = button.dataset.filter;
  document.querySelectorAll('.filter').forEach(item => {
    const selected = item === button;
    item.classList.toggle('active', selected);
    item.setAttribute('aria-pressed', String(selected));
  });
  render();
}));

$('#today-label').textContent = new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());
refresh().catch(error => { taskList.textContent = 'Não foi possível carregar as tarefas.'; notice(error.message, true); });
