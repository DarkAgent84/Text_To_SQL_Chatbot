document.addEventListener('DOMContentLoaded', () => {
  const chatFeed = document.getElementById('chatFeed');
  const welcomeScreen = document.getElementById('welcomeScreen');
  const questionInput = document.getElementById('questionInput');
  const btnSend = document.getElementById('btnSend');
  const sendIcon = document.getElementById('sendIcon');

  let activeChatId = null;
  let isRequestPending = false;

  // Auto-resize input textarea
  questionInput.addEventListener('input', () => {
    questionInput.style.height = 'auto';
    questionInput.style.height = Math.min(questionInput.scrollHeight, 140) + 'px';
  });

  // Handle Enter key (Shift+Enter for newline)
  questionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitQuestion();
    }
  });

  btnSend.addEventListener('click', submitQuestion);

  // Delegate click for suggestion chips
  document.addEventListener('click', (e) => {
    const chip = e.target.closest('.suggestion-chip');
    if (chip && chip.dataset.prompt) {
      questionInput.value = chip.dataset.prompt;
      submitQuestion();
    }
  });

  const dialectBadge = document.getElementById('dialectBadge');
  const modelBadge = document.getElementById('modelBadge');
  const dbProfileSelect = document.getElementById('dbProfileSelect');
  const welcomeDbTitle = document.getElementById('welcomeDbTitle');
  const welcomeDbSubtitle = document.getElementById('welcomeDbSubtitle');

  async function fetchSystemInfo() {
    try {
      const res = await fetch('/api/v1/system-info');
      if (res.ok) {
        const info = await res.json();
        if (dialectBadge && info.database) dialectBadge.textContent = info.database;
        if (modelBadge && info.active_model) modelBadge.textContent = info.active_model;
        if (welcomeDbTitle && info.reference_name) {
          welcomeDbTitle.textContent = `Query "${info.reference_name}"`;
        }
        if (welcomeDbSubtitle && info.dialect) {
          welcomeDbSubtitle.textContent = `Ask natural language questions against your ${info.dialect} database. AI dynamically inspects your schema with exact data types.`;
        }
      }
    } catch (e) {
      console.warn('Failed to load system info:', e);
    }
  }

  async function loadDatabaseProfiles() {
    if (!dbProfileSelect) return;
    try {
      const res = await fetch('/api/v1/connections');
      if (res.ok) {
        const list = await res.json();
        if (list && list.length > 0) {
          dbProfileSelect.innerHTML = list.map(c => `
            <option value="${c.id}" ${c.is_active ? 'selected' : ''}>
              ${c.is_active ? '● ' : ''}${c.reference_name} (${c.db_type.toUpperCase()})
            </option>
          `).join('');
          dbProfileSelect.style.display = 'inline-block';
        } else {
          dbProfileSelect.innerHTML = `<option value="">Default SQLite Database</option>`;
        }
      }
    } catch (e) {
      console.warn('Failed to load database profiles:', e);
    }
  }

  if (dbProfileSelect) {
    dbProfileSelect.addEventListener('change', async () => {
      const selectedId = dbProfileSelect.value;
      if (!selectedId) return;
      try {
        const res = await fetch(`/api/v1/connections/${selectedId}/activate`, { method: 'POST' });
        const data = await res.json();
        if (res.ok) {
          await fetchSystemInfo();
          await loadDatabaseProfiles();
          // Reset chat state for new database session
          activeChatId = null;
        } else {
          alert(data.detail || 'Could not switch database');
        }
      } catch (e) {
        console.error('Error switching database:', e);
      }
    });
  }

  fetchSystemInfo();
  loadDatabaseProfiles();

  async function submitQuestion() {
    const question = questionInput.value.trim();
    if (!question || isRequestPending) return;

    if (welcomeScreen) {
      welcomeScreen.style.display = 'none';
    }

    // Append User Message Bubble
    appendUserBubble(question);

    // Clear and reset input
    questionInput.value = '';
    questionInput.style.height = '58px';

    // Show Loading Bot Card
    const loadingCard = createLoadingCard();
    chatFeed.appendChild(loadingCard);
    scrollToBottom();

    setLoadingState(true);

    try {
      const response = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: question,
          chat_id: activeChatId
        })
      });

      const data = await response.json();
      loadingCard.remove();

      if (!response.ok || data.error) {
        appendErrorCard(data.error || 'An unexpected error occurred while processing your request.');
      } else {
        if (data["Chat Id"]) {
          activeChatId = data["Chat Id"];
        }
        if (dialectBadge && data["Database Used"]) {
          dialectBadge.textContent = data["Database Used"];
        }
        if (modelBadge && data["Model Used"]) {
          modelBadge.textContent = data["Model Used"];
        }
        appendBotCard(data);
      }
    } catch (err) {
      loadingCard.remove();
      appendErrorCard('Could not connect to the backend server. Please verify your connection.');
    } finally {
      setLoadingState(false);
      scrollToBottom();
    }
  }

  function setLoadingState(loading) {
    isRequestPending = loading;
    btnSend.disabled = loading;
    if (loading) {
      sendIcon.innerHTML = '<div class="spinner"></div>';
    } else {
      sendIcon.innerHTML = '➔';
    }
  }

  function appendUserBubble(text) {
    const group = document.createElement('div');
    group.className = 'msg-group';
    group.innerHTML = `<div class="user-bubble">${escapeHtml(text)}</div>`;
    chatFeed.appendChild(group);
  }

  function createLoadingCard() {
    const card = document.createElement('div');
    card.className = 'bot-card';
    card.innerHTML = `
      <div style="display: flex; align-items: center; gap: 12px; color: var(--text-muted);">
        <div class="spinner" style="border-top-color: var(--primary);"></div>
        <span>Generating SQL query & fetching business insights...</span>
      </div>
    `;
    return card;
  }

  function appendBotCard(data) {
    const card = document.createElement('div');
    card.className = 'bot-card';

    const answer = data["Answer"] || 'No answer generated.';
    const sql = data["SQL Query"] || '';
    const results = data["SQL Results"] || [];

    // 1. AI Answer Text
    const answerHtml = `<div class="bot-answer">${formatMarkdown(answer)}</div>`;

    // 2. Collapsible SQL Block
    let sqlHtml = '';
    if (sql) {
      sqlHtml = `
        <div class="sql-section">
          <div class="sql-header" onclick="toggleSql(this)">
            <span class="sql-title">⚡ Generated SQL Query</span>
            <button class="btn-copy" onclick="copyText(event, \`${escapeJs(sql)}\`)">
              <span>📋</span> Copy
            </button>
          </div>
          <div class="sql-code-container">${escapeHtml(sql)}</div>
        </div>
      `;
    }

    // 3. Data Table Block
    let tableHtml = '';
    if (Array.isArray(results) && results.length > 0) {
      const columns = Object.keys(results[0]);
      const tableRows = results.map(row => `
        <tr>
          ${columns.map(c => `<td>${escapeHtml(String(row[c] ?? ''))}</td>`).join('')}
        </tr>
      `).join('');

      tableHtml = `
        <div class="table-section">
          <div class="table-toolbar">
            <span class="table-info">Returned ${results.length} record(s)</span>
            <div style="display: flex; gap: 8px; align-items: center;">
              <input type="text" class="table-search" placeholder="Search results..." oninput="filterTable(this)">
              <button class="btn-export" onclick="exportData(this, 'csv')" title="Export results to CSV">
                <span>📥</span> CSV
              </button>
              <button class="btn-export" onclick="exportData(this, 'excel')" title="Export results to Excel">
                <span>📊</span> Excel
              </button>
            </div>
          </div>
          <div class="table-wrapper">
            <table class="data-table">
              <thead>
                <tr>${columns.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr>
              </thead>
              <tbody>
                ${tableRows}
              </tbody>
            </table>
          </div>
        </div>
      `;
    }

    // 4. Response Metadata Footer Tag
    const modelUsed = data["Model Used"] || 'Gemini AI';
    const dbUsed = data["Database Used"] || 'Database';
    const metaHtml = `
      <div style="margin-top: 12px; pt-8px; border-top: 1px solid var(--border-color, #e2e8f0); display: flex; gap: 16px; align-items: center; font-size: 0.78rem; color: var(--text-muted, #64748b);">
        <span>🤖 Model: <strong>${escapeHtml(modelUsed)}</strong></span>
        <span>💾 DB: <strong>${escapeHtml(dbUsed)}</strong></span>
      </div>
    `;

    card.innerHTML = answerHtml + sqlHtml + tableHtml + metaHtml;
    chatFeed.appendChild(card);
  }

  function appendErrorCard(errorMsg) {
    const card = document.createElement('div');
    card.className = 'bot-card';
    card.style.borderColor = 'var(--accent-rose)';
    card.innerHTML = `
      <div style="color: var(--accent-rose); font-weight: 600; display: flex; align-items: center; gap: 8px;">
        <span>⚠️</span> Error Processing Question
      </div>
      <div style="color: var(--text-muted); font-size: 0.9rem;">${escapeHtml(errorMsg)}</div>
    `;
    chatFeed.appendChild(card);
  }

  function scrollToBottom() {
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function escapeJs(str) {
    return String(str).replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$/g, '\\$');
  }

  function formatMarkdown(text) {
    return text
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n\n/g, '<br><br>')
      .replace(/\n/g, '<br>');
  }
});

// Global functions for inline HTML events
window.toggleSql = function(header) {
  const code = header.nextElementSibling;
  if (code) {
    code.style.display = code.style.display === 'none' ? 'block' : 'none';
  }
};

window.copyText = function(event, text) {
  event.stopPropagation();
  navigator.clipboard.writeText(text).then(() => {
    const btn = event.currentTarget;
    const oldText = btn.innerHTML;
    btn.innerHTML = '<span>✓</span> Copied!';
    setTimeout(() => { btn.innerHTML = oldText; }, 2000);
  });
};

window.filterTable = function(input) {
  const filter = input.value.toLowerCase();
  const table = input.closest('.table-section').querySelector('.data-table');
  const rows = table.querySelectorAll('tbody tr');

  rows.forEach(row => {
    const text = row.textContent.toLowerCase();
    row.style.display = text.includes(filter) ? '' : 'none';
  });
};

window.exportData = function(btn, format) {
  const tableSection = btn.closest('.table-section');
  const table = tableSection.querySelector('.data-table');
  if (!table) return;

  const headers = Array.from(table.querySelectorAll('thead th')).map(th => th.innerText.trim());
  const rows = Array.from(table.querySelectorAll('tbody tr')).filter(tr => tr.style.display !== 'none');

  const csvRows = [];
  csvRows.push(headers.map(h => `"${h.replace(/"/g, '""')}"`).join(','));

  rows.forEach(row => {
    const cells = Array.from(row.querySelectorAll('td')).map(td => `"${td.innerText.replace(/"/g, '""')}"`);
    csvRows.push(cells.join(','));
  });

  const content = '\uFEFF' + csvRows.join('\n'); // UTF-8 BOM for Excel compatibility
  const mimeType = format === 'excel' ? 'application/vnd.ms-excel;charset=utf-8;' : 'text/csv;charset=utf-8;';
  const extension = format === 'excel' ? 'csv' : 'csv';

  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  
  const timestamp = new Date().toISOString().slice(0, 10);
  link.href = url;
  link.setAttribute('download', `query_results_${timestamp}.${extension}`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

