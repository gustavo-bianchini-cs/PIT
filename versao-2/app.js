const state = { tasks: [], filter: 'all', search: '', sort: 'due', editingId: null, formSnapshot: '' };
const $ = (selector) => document.querySelector(selector);
const taskList = $('#task-list');
const dialog = $('#task-dialog');
const form = $('#task-form');
const toast = $('#toast');
const PRIORITY = { alta: { label: 'Alta', rank: 0 }, media: { label: 'Média', rank: 1 }, baixa: { label: 'Baixa', rank: 2 } };
const OFFLINE_MESSAGE = 'Sem conexão com o servidor. Verifique se a Agenda Acadêmica está em execução e tente novamente.';
const HOUR = 3600000;
const END_OF_DAY = '23:59'; // tarefa sem horário: o prazo vale até o fim do dia
let toastTimer;
let pointerStartedOnBackdrop = false;

function notice(message, isError = false) {
  toast.textContent = message;
  toast.classList.toggle('error', isError);
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), isError ? 6000 : 3500);
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    });
  } catch {
    // O fetch só falha aqui quando o servidor não responde (aplicação fechada ou sem rede).
    // Antes, o navegador mostrava a mensagem técnica em inglês "Failed to fetch".
    throw new Error(OFFLINE_MESSAGE);
  }
  let body;
  try { body = await response.json(); } catch { throw new Error('Não foi possível ler a resposta do servidor.'); }
  if (!response.ok) throw new Error(body.error || 'Não foi possível concluir esta ação.');
  return body;
}

function todayISO() {
  const now = new Date();
  return [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
}

function parseDate(value) {
  const [year, month, day] = value.split('-').map(Number);
  return new Date(year, month - 1, day);
}

function formatDate(value) {
  return new Intl.DateTimeFormat('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' }).format(parseDate(value));
}

// Dias entre hoje e o prazo: 0 = hoje, 1 = amanhã, negativo = atrasada.
function daysUntil(value) {
  return Math.round((parseDate(value) - parseDate(todayISO())) / 86400000);
}

// Momento exato do prazo: data + horário (sem horário, 23:59 do dia).
function deadline(task) {
  const moment = parseDate(task.due_date);
  const [hours, minutes] = (task.due_time || END_OF_DAY).split(':').map(Number);
  moment.setHours(hours, minutes, 0, 0);
  return moment;
}

function isOverdue(task) {
  return !task.completed && deadline(task) <= new Date();
}

// Cor do cartão pelo tempo que falta (sugestão dos testes): verde com folga, amarelo a partir de 6 horas,
// laranja na última hora e vermelho quando o prazo acaba. Tarefas concluídas ficam sem cor.
function urgency(task) {
  if (task.completed) return '';
  const left = deadline(task) - new Date();
  if (left <= 0) return 'late';
  if (left <= HOUR) return 'last-hour';
  if (left <= 6 * HOUR) return 'six-hours';
  return 'ok';
}

function timeLeft(milliseconds) {
  const minutes = Math.max(1, Math.ceil(milliseconds / 60000));
  if (minutes < 60) return `${minutes === 1 ? 'Falta' : 'Faltam'} ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${hours === 1 && !rest ? 'Falta' : 'Faltam'} ${hours} h${rest ? ` ${rest} min` : ''}`;
}

function dueInfo(task) {
  const time = task.due_time ? ` às ${task.due_time}` : '';
  const date = formatDate(task.due_date) + time;
  if (task.completed) return { text: `Concluída · prazo ${date}`, tone: '' };
  const level = urgency(task);
  const days = daysUntil(task.due_date);
  if (level === 'late') {
    if (days < 0) return { text: `Atrasada há ${-days} ${days === -1 ? 'dia' : 'dias'} · ${date}`, tone: 'overdue' };
    return { text: `Prazo encerrado hoje às ${task.due_time || END_OF_DAY}`, tone: 'overdue' };
  }
  if (level !== 'ok') {
    const until = `até ${task.due_time || END_OF_DAY}${days === 1 ? ' de amanhã' : ''}`;
    return { text: `${timeLeft(deadline(task) - new Date())} · ${until}`, tone: level };
  }
  if (days === 0) return { text: `Vence hoje${time}`, tone: 'soon' };
  if (days === 1) return { text: `Vence amanhã${time}`, tone: 'soon' };
  if (days <= 7) return { text: `Faltam ${days} dias · ${date}`, tone: '' };
  return { text: `Entrega · ${date}`, tone: '' };
}

// Busca sem diferenciar maiúsculas, minúsculas e acentos: "calculo" encontra "Cálculo".
function normalize(text) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
}

function matchesFilter(task) {
  if (state.filter === 'pending') return !task.completed;
  if (state.filter === 'completed') return task.completed;
  if (state.filter === 'overdue') return isOverdue(task);
  return true;
}

function matchesSearch(task) {
  const terms = normalize(state.search).split(/\s+/).filter(Boolean);
  const text = normalize(`${task.title} ${task.subject} ${task.notes}`);
  return terms.every(term => text.includes(term));
}

function compareTasks(a, b) {
  if (a.completed !== b.completed) return a.completed ? 1 : -1;
  const dueKey = task => `${task.due_date} ${task.due_time || END_OF_DAY}`;
  const byDue = dueKey(a).localeCompare(dueKey(b));
  const byPriority = PRIORITY[a.priority].rank - PRIORITY[b.priority].rank;
  if (state.sort === 'priority') return byPriority || byDue;
  if (state.sort === 'subject') return a.subject.localeCompare(b.subject, 'pt-BR', { sensitivity: 'base' }) || byDue;
  return byDue || byPriority;
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

function emptyState(heading, message) {
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  const illustration = document.createElement('div');
  illustration.className = 'empty-illustration';
  illustration.setAttribute('aria-hidden', 'true');
  illustration.textContent = '✎';
  const title = document.createElement('h3');
  title.textContent = heading;
  const text = document.createElement('p');
  text.textContent = message;
  empty.append(illustration, title, text);
  return empty;
}

function taskRow(task) {
  const row = document.createElement('article');
  const level = urgency(task);
  row.className = `task-row${task.completed ? ' completed' : ''}${level ? ` deadline-${level}` : ''}`;
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
  const priority = document.createElement('span');
  priority.className = `priority-pill ${task.priority}`;
  priority.textContent = `Prioridade ${PRIORITY[task.priority].label.toLowerCase()}`;
  const info = dueInfo(task);
  const due = document.createElement('span');
  due.className = `due-date ${info.tone}`.trim();
  due.textContent = info.text;
  meta.append(subject, priority, due);
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
  return row;
}

// Sugere as disciplinas já cadastradas para evitar "Matemática" e "matematica" como itens diferentes.
function updateSubjectOptions() {
  const subjects = [...new Set(state.tasks.map(t => t.subject))].sort((a, b) => a.localeCompare(b, 'pt-BR'));
  $('#subject-options').replaceChildren(...subjects.map(value => Object.assign(document.createElement('option'), { value })));
}

function render() {
  const tasks = state.tasks;
  $('#total-count').textContent = tasks.length;
  $('#pending-count').textContent = tasks.filter(t => !t.completed).length;
  $('#overdue-count').textContent = tasks.filter(isOverdue).length;
  $('#completed-count').textContent = tasks.filter(t => t.completed).length;
  updateSubjectOptions();
  const search = state.search.trim();
  const visible = tasks.filter(t => matchesFilter(t) && matchesSearch(t)).sort(compareTasks);
  $('#result-info').textContent = search
    ? `${visible.length} ${visible.length === 1 ? 'tarefa encontrada' : 'tarefas encontradas'} para “${search}”.`
    : '';
  taskList.replaceChildren();
  if (visible.length > 0) {
    taskList.append(...visible.map(taskRow));
  } else if (tasks.length === 0) {
    taskList.append(emptyState('Sua agenda começa aqui', 'Adicione sua primeira tarefa para organizar seus próximos prazos.'));
  } else if (search) {
    taskList.append(emptyState('Nenhuma tarefa encontrada', 'Confira a escrita, tente outra palavra ou limpe a busca.'));
  } else {
    taskList.append(emptyState('Nenhuma tarefa nesta lista', 'Escolha outro filtro para ver suas tarefas.'));
  }
}

async function refresh() {
  const body = await api('/api/tasks');
  state.tasks = body.tasks;
  render();
}

function formValues() {
  return {
    title: $('#title').value.trim(), subject: $('#subject').value.trim(),
    due_date: $('#due-date').value, due_time: $('#due-time').value,
    priority: $('#priority').value, notes: $('#notes').value.trim(),
  };
}

function hasUnsavedChanges() {
  return dialog.open && JSON.stringify(formValues()) !== state.formSnapshot;
}

function updateNotesCount() {
  $('#notes-count').textContent = `${$('#notes').value.length}/500`;
}

// Erros do formulário aparecem dentro dele: o aviso no canto da tela ficava atrás do fundo escuro da janela.
function showFormError(message = '') {
  const box = $('#form-error');
  box.textContent = message;
  box.hidden = !message;
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
    $('#due-time').value = task.due_time || '';
    $('#priority').value = task.priority;
    $('#notes').value = task.notes;
  }
  updateNotesCount();
  showFormError();
  state.formSnapshot = JSON.stringify(formValues());
  dialog.showModal();
  $('#title').focus();
}

// Antes, clicar fora da janela ou apertar Esc fechava o formulário e apagava o que foi digitado.
function closeForm({ force = false } = {}) {
  if (!force && hasUnsavedChanges() && !confirm('Descartar as alterações que ainda não foram salvas?')) return;
  dialog.close();
}

$('#new-task').addEventListener('click', () => openForm());
$('#close-dialog').addEventListener('click', () => closeForm());
$('#cancel-dialog').addEventListener('click', () => closeForm());
$('#notes').addEventListener('input', updateNotesCount);
// Só fecha pelo fundo escuro se o clique começou nele (arrastar a seleção de texto para fora não fecha).
dialog.addEventListener('pointerdown', event => { pointerStartedOnBackdrop = event.target === dialog; });
dialog.addEventListener('click', event => { if (event.target === dialog && pointerStartedOnBackdrop) closeForm(); });
dialog.addEventListener('cancel', event => { event.preventDefault(); closeForm(); });
dialog.addEventListener('close', () => { state.editingId = null; });

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  const editingId = state.editingId;
  const existing = state.tasks.find(t => t.id === editingId);
  const payload = { ...formValues(), completed: existing?.completed ?? false };
  const dateChanged = payload.due_date !== existing?.due_date || payload.due_time !== (existing?.due_time ?? '');
  const when = formatDate(payload.due_date) + (payload.due_time ? ` às ${payload.due_time}` : '');
  if (!payload.completed && dateChanged && deadline(payload) <= new Date()
      && !confirm(`A data de entrega (${when}) já passou. Deseja salvar mesmo assim?`)) {
    $(payload.due_date < todayISO() ? '#due-date' : '#due-time').focus();
    return;
  }
  const submit = $('#save-task');
  submit.disabled = true;
  showFormError();
  try {
    await api(editingId ? `/api/tasks/${editingId}` : '/api/tasks', {
      method: editingId ? 'PUT' : 'POST', body: JSON.stringify(payload),
    });
  } catch (error) {
    showFormError(error.message);
    submit.disabled = false;
    return;
  }
  closeForm({ force: true });
  notice(existing ? 'Tarefa atualizada.' : 'Tarefa criada.');
  submit.disabled = false;
  try { await refresh(); } catch (error) { notice(error.message, true); }
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

$('#search').addEventListener('input', event => { state.search = event.target.value; render(); });
$('#sort').addEventListener('change', event => { state.sort = event.target.value; render(); });

// As cores dependem da hora: a lista é redesenhada a cada minuto, sem precisar recarregar a página.
setInterval(() => { if (!document.hidden) render(); }, 60000);

$('#today-label').textContent = new Intl.DateTimeFormat('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());
refresh().catch(error => { taskList.textContent = 'Não foi possível carregar as tarefas.'; notice(error.message, true); });
