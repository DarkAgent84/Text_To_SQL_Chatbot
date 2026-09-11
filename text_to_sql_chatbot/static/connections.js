document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const dbTypeCards = document.querySelectorAll('.db-type-card');
  const dbTypeInput = document.getElementById('dbTypeInput');
  const networkFields = document.querySelectorAll('.network-fields');
  const sqliteFields = document.querySelectorAll('.sqlite-fields');

  const refNameInput = document.getElementById('refNameInput');
  const hostInput = document.getElementById('hostInput');
  const portInput = document.getElementById('portInput');
  const dbNameInput = document.getElementById('dbNameInput');
  const userInput = document.getElementById('userInput');
  const passInput = document.getElementById('passInput');
  const sqlitePathInput = document.getElementById('sqlitePathInput');
  const setActiveCheckbox = document.getElementById('setActiveCheckbox');
  const editConnectionId = document.getElementById('editConnectionId');

  const form = document.getElementById('dbConnectionForm');
  const formTitle = document.getElementById('formTitle');
  const saveBtnText = document.getElementById('saveBtnText');
  const btnResetForm = document.getElementById('btnResetForm');
  const btnTogglePwd = document.getElementById('btnTogglePwd');

  const btnTestConn = document.getElementById('btnTestConn');
  const testSpinner = document.getElementById('testSpinner');
  const saveSpinner = document.getElementById('saveSpinner');
  const testFeedbackBox = document.getElementById('testFeedbackBox');
  const feedbackBadge = document.getElementById('feedbackBadge');
  const feedbackLatency = document.getElementById('feedbackLatency');
  const feedbackBody = document.getElementById('feedbackBody');
  const feedbackTables = document.getElementById('feedbackTables');

  const savedConnectionsList = document.getElementById('savedConnectionsList');
  const btnRefreshList = document.getElementById('btnRefreshList');
  const activeDbBadge = document.getElementById('activeDbBadge');

  // Database Type Switching
  dbTypeCards.forEach(card => {
    card.addEventListener('click', () => {
      dbTypeCards.forEach(c => c.classList.remove('active'));
      card.classList.add('active');

      const selectedType = card.dataset.type;
      dbTypeInput.value = selectedType;

      if (selectedType === 'sqlite') {
        networkFields.forEach(el => el.style.display = 'none');
        sqliteFields.forEach(el => el.style.display = 'block');
      } else {
        networkFields.forEach(el => el.style.display = 'flex');
        sqliteFields.forEach(el => el.style.display = 'none');

        if (selectedType === 'postgresql') {
          if (!portInput.value || portInput.value === '3306') portInput.value = '5432';
          if (!userInput.value || userInput.value === 'root') userInput.value = 'postgres';
        } else if (selectedType === 'mysql') {
          if (!portInput.value || portInput.value === '5432') portInput.value = '3306';
          if (!userInput.value || userInput.value === 'postgres') userInput.value = 'root';
        }
      }

      hideFeedback();
    });
  });

  // Password Visibility Toggle
  btnTogglePwd.addEventListener('click', () => {
    if (passInput.type === 'password') {
      passInput.type = 'text';
      btnTogglePwd.textContent = '🙈';
    } else {
      passInput.type = 'password';
      btnTogglePwd.textContent = '👁️';
    }
  });

  // Reset / Clear Form
  function resetForm() {
    form.reset();
    editConnectionId.value = '';
    formTitle.textContent = '➕ Connect New Database';
    saveBtnText.textContent = '💾 Save & Connect';
    btnResetForm.style.display = 'none';

    // Default to postgresql
    const defaultCard = document.querySelector('.db-type-card[data-type="postgresql"]');
    if (defaultCard) defaultCard.click();
    hideFeedback();
  }

  btnResetForm.addEventListener('click', resetForm);

  // Helper: Build Payload from Form
  function getFormData() {
    const type = dbTypeInput.value;
    const isSqlite = type === 'sqlite';

    return {
      reference_name: refNameInput.value.trim(),
      db_type: type,
      host: isSqlite ? null : hostInput.value.trim() || 'localhost',
      port: isSqlite ? null : parseInt(portInput.value, 10) || (type === 'mysql' ? 3306 : 5432),
      database_name: isSqlite ? null : dbNameInput.value.trim(),
      username: isSqlite ? null : userInput.value.trim(),
      password: isSqlite ? null : passInput.value,
      extra_params: isSqlite ? sqlitePathInput.value.trim() : null,
      set_as_active: setActiveCheckbox.checked
    };
  }

  function hideFeedback() {
    testFeedbackBox.style.display = 'none';
  }

  function showFeedback(status, message, latency = null, tables = []) {
    testFeedbackBox.style.display = 'block';
    if (status === 'success') {
      testFeedbackBox.className = 'test-feedback-box feedback-success';
      feedbackBadge.textContent = '✓ Connection Successful';
      feedbackBadge.className = 'feedback-badge badge-success';
      feedbackLatency.textContent = latency ? `⚡ ${latency} ms` : '';
      feedbackBody.textContent = message || `Successfully connected. Discovered ${tables.length} tables.`;

      if (tables && tables.length > 0) {
        feedbackTables.innerHTML = `
          <div class="feedback-tables-title">Discovered Tables preview:</div>
          <div class="table-pill-wrap">
            ${tables.map(t => `<span class="table-pill">${t}</span>`).join('')}
          </div>
        `;
      } else {
        feedbackTables.innerHTML = '';
      }
    } else {
      testFeedbackBox.className = 'test-feedback-box feedback-error';
      feedbackBadge.textContent = '✕ Connection Failed';
      feedbackBadge.className = 'feedback-badge badge-error';
      feedbackLatency.textContent = '';
      feedbackBody.textContent = message || 'Could not connect with provided details. Check host, port, and credentials.';
      feedbackTables.innerHTML = '';
    }
  }

  // Live Test Connection
  btnTestConn.addEventListener('click', async () => {
    const data = getFormData();
    if (!data.db_type) return;

    btnTestConn.disabled = true;
    testSpinner.style.display = 'inline-block';
    hideFeedback();

    try {
      const res = await fetch('/api/v1/connections/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });

      const result = await res.json();
      if (res.ok && result.status === 'success') {
        showFeedback(
          'success',
          `Successfully connected to ${data.db_type.toUpperCase()} database. Ready for AI query generation.`,
          result.latency_ms,
          result.tables
        );
      } else {
        showFeedback('error', result.error || 'Connection attempt failed.');
      }
    } catch (err) {
      showFeedback('error', 'Network error reaching backend server.');
    } finally {
      btnTestConn.disabled = false;
      testSpinner.style.display = 'none';
    }
  });

  // Save / Update Connection
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const data = getFormData();
    if (!data.reference_name) {
      alert('Please provide a Reference Name for this connection.');
      return;
    }

    const connId = editConnectionId.value;
    const isEdit = Boolean(connId);

    btnSaveConn.disabled = true;
    saveSpinner.style.display = 'inline-block';

    try {
      const url = isEdit ? `/api/v1/connections/${connId}` : '/api/v1/connections';
      const method = isEdit ? 'PUT' : 'POST';

      const res = await fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });

      const result = await res.json();
      if (!res.ok) {
        showFeedback('error', result.detail || result.error || 'Failed to save connection.');
        return;
      }

      // If requested to activate
      if (data.set_as_active && result.id) {
        await activateConnection(result.id, false);
      }

      resetForm();
      await fetchSavedConnections();
      await fetchActiveConnection();
      showToast('Database connection saved successfully!', 'success');
    } catch (err) {
      showFeedback('error', 'Network error saving connection profile.');
    } finally {
      btnSaveConn.disabled = false;
      saveSpinner.style.display = 'none';
    }
  });

  // Fetch Saved Connections
  async function fetchSavedConnections() {
    try {
      const res = await fetch('/api/v1/connections');
      if (!res.ok) throw new Error('Failed to load');
      const connections = await res.json();
      renderConnectionsList(connections);
    } catch (err) {
      savedConnectionsList.innerHTML = `
        <div class="conn-empty-state">
          <div class="empty-icon">⚠️</div>
          <div class="empty-title">Could not load saved profiles</div>
          <div class="empty-desc">Check if the backend server is running.</div>
        </div>
      `;
    }
  }

  // Render Saved Connections Cards
  function renderConnectionsList(connections) {
    if (!connections || connections.length === 0) {
      savedConnectionsList.innerHTML = `
        <div class="conn-empty-state">
          <div class="empty-icon">📂</div>
          <div class="empty-title">No saved database connections</div>
          <div class="empty-desc">Fill out the form on the left to add your first database.</div>
        </div>
      `;
      return;
    }

    savedConnectionsList.innerHTML = connections.map(conn => {
      const isSqlite = conn.db_type === 'sqlite';
      const typeIcons = { postgresql: '🐘', postgres: '🐘', mysql: '🐬', sqlite: '🪶' };
      const icon = typeIcons[conn.db_type] || '🗄️';

      const subtitle = isSqlite
        ? `Path: ${conn.extra_params || 'app.db'}`
        : `${conn.username || 'user'}@${conn.host || 'localhost'}:${conn.port || ''} / ${conn.database_name || ''}`;

      return `
        <div class="conn-card ${conn.is_active ? 'active-profile' : ''}" data-id="${conn.id}">
          <div class="conn-card-main">
            <div class="conn-card-header">
              <div class="conn-title-wrap">
                <span class="conn-icon">${icon}</span>
                <span class="conn-title">${escapeHtml(conn.reference_name)}</span>
              </div>
              <div class="conn-badges">
                <span class="badge badge-db-type">${conn.db_type.toUpperCase()}</span>
                ${conn.is_active ? '<span class="badge badge-active">● ACTIVE</span>' : ''}
              </div>
            </div>
            <div class="conn-meta">${escapeHtml(subtitle)}</div>
          </div>
          <div class="conn-card-actions">
            ${
              conn.is_active
                ? `<button class="btn-sm btn-active-indicator" disabled>✓ Connected</button>`
                : `<button class="btn-sm btn-connect" onclick="window.handleActivate(${conn.id})">⚡ Connect</button>`
            }
            <button class="btn-sm btn-outline" onclick="window.handleEdit(${conn.id})" title="Edit Connection">✏️ Edit</button>
            <button class="btn-sm btn-danger" onclick="window.handleDelete(${conn.id})" title="Delete Connection">🗑️</button>
          </div>
        </div>
      `;
    }).join('');
  }

  // Activate Connection Profile
  window.handleActivate = async (id) => {
    await activateConnection(id, true);
  };

  async function activateConnection(id, refreshUI = true) {
    try {
      const res = await fetch(`/api/v1/connections/${id}/activate`, {
        method: 'POST'
      });
      const data = await res.json();
      if (!res.ok) {
        alert(data.detail || 'Failed to activate connection');
        return;
      }
      if (refreshUI) {
        showToast(`Activated: ${data.connection.reference_name}`, 'success');
        await fetchSavedConnections();
        await fetchActiveConnection();
      }
    } catch (err) {
      alert('Error activating database profile.');
    }
  }

  // Edit Connection Profile
  window.handleEdit = async (id) => {
    try {
      const res = await fetch('/api/v1/connections');
      const list = await res.json();
      const conn = list.find(c => c.id === id);
      if (!conn) return;

      editConnectionId.value = conn.id;
      refNameInput.value = conn.reference_name;
      formTitle.textContent = `✏️ Edit: ${conn.reference_name}`;
      saveBtnText.textContent = '💾 Update Connection';
      btnResetForm.style.display = 'inline-block';

      // Pick DB type
      const targetCard = document.querySelector(`.db-type-card[data-type="${conn.db_type}"]`);
      if (targetCard) targetCard.click();

      if (conn.db_type !== 'sqlite') {
        hostInput.value = conn.host || 'localhost';
        portInput.value = conn.port || (conn.db_type === 'mysql' ? 3306 : 5432);
        dbNameInput.value = conn.database_name || '';
        userInput.value = conn.username || '';
        passInput.value = ''; // keep empty unless user updates
      } else {
        sqlitePathInput.value = conn.extra_params || './app.db';
      }

      setActiveCheckbox.checked = conn.is_active;
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      console.error(e);
    }
  };

  // Delete Connection Profile
  window.handleDelete = async (id) => {
    if (!confirm('Are you sure you want to delete this saved connection profile?')) return;
    try {
      const res = await fetch(`/api/v1/connections/${id}`, { method: 'DELETE' });
      if (res.ok) {
        showToast('Connection profile deleted', 'info');
        await fetchSavedConnections();
        await fetchActiveConnection();
      }
    } catch (e) {
      alert('Failed to delete connection.');
    }
  };

  // Fetch Active Connection Badge in Header
  async function fetchActiveConnection() {
    try {
      const res = await fetch('/api/v1/system-info');
      if (res.ok) {
        const info = await res.json();
        if (activeDbBadge) {
          activeDbBadge.textContent = info.database || 'Active Database';
        }
      }
    } catch (e) {
      console.warn(e);
    }
  }

  // Toast Notification Helper
  function showToast(msg, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `app-toast toast-${type}`;
    toast.textContent = msg;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('visible'), 10);
    setTimeout(() => {
      toast.classList.remove('visible');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  btnRefreshList.addEventListener('click', fetchSavedConnections);

  // Initial Data Load
  fetchSavedConnections();
  fetchActiveConnection();
});
