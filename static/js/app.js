/* ─── IOCL Lab Assistant — Frontend Logic ──────────────────────────────────── */

/* ═══ State ═══════════════════════════════════════════════════════════════════ */
const state = {
  currentPage: 'dashboard',
  selectedFile: null,
  chatHistory: JSON.parse(localStorage.getItem('lab_history') || '[]'),
  sending: false,
};

/* ═══ Utilities ═══════════════════════════════════════════════════════════════ */
function $(id) { return document.getElementById(id); }

function showToast(msg, type = '') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast show ${type}`;
  setTimeout(() => { t.className = 'toast'; }, 3500);
}

function formatDate(isoStr) {
  if (!isoStr) return '—';
  const [y, m, d] = isoStr.slice(0,10).split('-');
  return `${d}-${m}-${y}`;
}

function shiftBadge(shift) {
  if (!shift) return `<span class="shift-badge unknown">—</span>`;
  if (shift === 'M') return `<span class="shift-badge morning">🌅 Morning</span>`;
  if (shift === 'E') return `<span class="shift-badge evening">🌆 Evening</span>`;
  return `<span class="shift-badge unknown">${shift}</span>`;
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ═══ Navigation ══════════════════════════════════════════════════════════════ */
function navigate(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const pageEl = $(`page-${page}`);
  const navEl  = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (pageEl) pageEl.classList.add('active');
  if (navEl)  navEl.classList.add('active');

  state.currentPage = page;

  if (page === 'dashboard') loadDashboard();
  if (page === 'history')   renderHistory();
}

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    navigate(item.dataset.page);
  });
});

/* ═══ Dashboard ═══════════════════════════════════════════════════════════════ */
async function loadDashboard() {
  // Greeting
  const hour = new Date().getHours();
  const greet = hour < 12 ? 'Good Morning' : hour < 17 ? 'Good Afternoon' : 'Good Evening';
  const today = new Date().toLocaleDateString('en-GB', { day:'2-digit', month:'long', year:'numeric' });
  $('dash-greeting').textContent = `${greet} — ${today}`;

  try {
    const res  = await fetch('/api/stats');
    const data = await res.json();

    $('stat-reports').textContent  = data.total_reports  ?? 0;
    $('stat-records').textContent  = data.total_records  ?? 0;
    $('stat-morning').textContent  = data.morning_count  ?? 0;
    $('stat-evening').textContent  = data.evening_count  ?? 0;

    renderReportsTable(data.recent_reports || []);
    updateApiStatus(true);
  } catch {
    updateApiStatus(false);
  }
}

function renderReportsTable(reports) {
  const tbody = $('reports-tbody');
  if (!reports.length) {
    tbody.innerHTML = `<tr><td colspan="7"><div class="empty-state"><div class="empty-icon">📂</div><p>No reports uploaded yet.</p></div></td></tr>`;
    return;
  }
  tbody.innerHTML = reports.map(r => `
    <tr>
      <td title="${escapeHtml(r.original_file_name)}" style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
        ${escapeHtml((r.original_file_name || '').slice(0, 38))}${r.original_file_name?.length > 38 ? '…' : ''}
      </td>
      <td>${formatDate(r.report_date)}</td>
      <td>${shiftBadge(r.shift)}</td>
      <td><strong>${r.result_count ?? 0}</strong></td>
      <td>${escapeHtml(r.uploaded_by || '—')}</td>
      <td style="color:var(--text-muted)">${formatDate(r.expires_at)}</td>
      <td>
        <button class="btn btn-ghost" onclick="deleteReport('${r.report_id}')">🗑️ Delete</button>
      </td>
    </tr>
  `).join('');
}

async function deleteReport(id) {
  if (!confirm('Delete this report and all its data?')) return;
  try {
    await fetch(`/api/reports/${id}`, { method: 'DELETE' });
    showToast('Report deleted.', '');
    loadDashboard();
  } catch {
    showToast('Failed to delete.', 'error');
  }
}

/* ═══ Upload ══════════════════════════════════════════════════════════════════ */

// Set today's date as default
const today = new Date().toISOString().slice(0, 10);
$('report-date').value = today;

const dropzone = $('dropzone');
const fileInput = $('file-input');

dropzone.addEventListener('click', () => fileInput.click());

dropzone.addEventListener('dragover', e => {
  e.preventDefault();
  dropzone.classList.add('drag-over');
});
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('drag-over'));
dropzone.addEventListener('drop', e => {
  e.preventDefault();
  dropzone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelected(file);
});

fileInput.addEventListener('change', () => {
  if (fileInput.files[0]) handleFileSelected(fileInput.files[0]);
});

function handleFileSelected(file) {
  state.selectedFile = file;
  $('file-selected').classList.add('show');
  $('file-selected-name').textContent = file.name;
  $('file-selected-size').textContent = formatBytes(file.size);
  $('upload-btn').disabled = false;

  // Auto-detect date from filename
  const dateMatch = file.name.match(/(\d{2})[.\-/](\d{2})[.\-/](\d{4})/);
  if (dateMatch) {
    const [, dd, mm, yyyy] = dateMatch;
    $('report-date').value = `${yyyy}-${mm}-${dd}`;
  }

  // Reset result banner
  const res = $('upload-result');
  res.className = 'upload-result';
}

function formatBytes(b) {
  if (b < 1024)       return `${b} B`;
  if (b < 1048576)    return `${(b/1024).toFixed(1)} KB`;
  return `${(b/1048576).toFixed(1)} MB`;
}

$('upload-btn').addEventListener('click', async () => {
  if (!state.selectedFile) return;

  $('upload-btn').disabled = true;
  $('upload-btn-text').innerHTML = '<span class="spinner"></span> Parsing…';

  const form = new FormData();
  form.append('file', state.selectedFile);
  form.append('report_date', $('report-date').value);
  form.append('uploaded_by', $('uploaded-by').value || 'Unknown');

  try {
    const res  = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();
    const box  = $('upload-result');

    if (data.success) {
      box.className = 'upload-result success';
      $('upload-result-title').textContent = `✅ ${data.file_name} uploaded successfully!`;
      $('upload-result-detail').textContent =
        `Extracted ${data.records_extracted} parameter records.`;
      $('upload-meta-row').innerHTML = `
        <div class="upload-meta-item">📅 Date: <span>${formatDate(data.detected_date)}</span></div>
        <div class="upload-meta-item">🕐 Shift: <span>${data.detected_shift}</span></div>
        <div class="upload-meta-item">⏳ Expires in 7 days</div>
      `;
      showToast('Report saved successfully!');

      // Reset
      state.selectedFile = null;
      fileInput.value = '';
      $('file-selected').classList.remove('show');
    } else {
      box.className = 'upload-result error';
      $('upload-result-title').textContent = '❌ Upload failed';
      $('upload-result-detail').textContent = data.error || 'Unknown error.';
      $('upload-meta-row').innerHTML = '';
      showToast(data.error || 'Upload failed.', 'error');
    }
  } catch (err) {
    showToast('Network error. Is the server running?', 'error');
  }

  $('upload-btn-text').innerHTML = '📥 Upload &amp; Parse';
  $('upload-btn').disabled = false;
});

/* ═══ Chat ════════════════════════════════════════════════════════════════════ */

function appendMessage(role, text) {
  const messages = $('chat-messages');
  const div = document.createElement('div');
  div.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? 'U' : '🔬';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = text;

  div.appendChild(avatar);
  div.appendChild(bubble);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function showTyping() {
  const messages = $('chat-messages');
  const div = document.createElement('div');
  div.className = 'message assistant';
  div.id = 'typing-indicator';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = '🔬';

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble typing-dots';
  bubble.innerHTML = '<span></span><span></span><span></span>';

  div.appendChild(avatar);
  div.appendChild(bubble);
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
}

function removeTyping() {
  const el = $('typing-indicator');
  if (el) el.remove();
}

async function sendMessage(question) {
  if (!question.trim() || state.sending) return;
  state.sending = true;
  $('chat-send-btn').disabled = true;
  $('chat-input').value = '';

  appendMessage('user', question);
  showTyping();

  try {
    const res  = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    const data = await res.json();
    removeTyping();

    const answer = data.response || data.error || 'No response received.';
    appendMessage('assistant', answer);

    // Save to history
    state.chatHistory.unshift({
      question,
      answer,
      ts: new Date().toLocaleString('en-GB', {
        day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit'
      }),
    });
    if (state.chatHistory.length > 50) state.chatHistory.pop();
    localStorage.setItem('lab_history', JSON.stringify(state.chatHistory));

  } catch {
    removeTyping();
    appendMessage('assistant', '⚠️ Could not reach the server. Is it running?');
  }

  state.sending = false;
  $('chat-send-btn').disabled = false;
}

$('chat-send-btn').addEventListener('click', () => {
  sendMessage($('chat-input').value.trim());
});

$('chat-input').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage($('chat-input').value.trim());
  }
});

// Auto-resize textarea
$('chat-input').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});

// Suggestion chips
document.querySelectorAll('.suggestion-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const q = chip.dataset.q;
    navigate('chat');
    sendMessage(q);
  });
});

/* ═══ History ═════════════════════════════════════════════════════════════════ */

function renderHistory(filter = '') {
  const list = $('history-list');
  const items = filter
    ? state.chatHistory.filter(h =>
        h.question.toLowerCase().includes(filter.toLowerCase()))
    : state.chatHistory;

  if (!items.length) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">💬</div><p>No queries yet.</p></div>`;
    return;
  }

  list.innerHTML = items.map((h, i) => `
    <div class="history-item" onclick="toggleHistory(${i})">
      <div class="history-question">
        <span style="font-size:14px;opacity:0.5;">💬</span>
        <span class="history-q-text">${escapeHtml(h.question)}</span>
        <span class="history-ts">${h.ts}</span>
      </div>
      <div class="history-answer" id="hist-ans-${i}">${escapeHtml(h.answer)}</div>
    </div>
  `).join('');
}

function toggleHistory(i) {
  const el = $(`hist-ans-${i}`);
  if (el) el.classList.toggle('open');
}

$('history-search').addEventListener('input', function () {
  renderHistory(this.value);
});

$('clear-history-btn').addEventListener('click', () => {
  if (!confirm('Clear all history?')) return;
  state.chatHistory = [];
  localStorage.removeItem('lab_history');
  renderHistory();
  showToast('History cleared.');
});

/* ═══ API Status ══════════════════════════════════════════════════════════════ */
function updateApiStatus(ok) {
  $('api-dot').className = `status-dot ${ok ? 'ok' : 'err'}`;
  $('api-label').textContent = ok ? 'Connected' : 'Offline';
}

/* ═══ Init ════════════════════════════════════════════════════════════════════ */
loadDashboard();
