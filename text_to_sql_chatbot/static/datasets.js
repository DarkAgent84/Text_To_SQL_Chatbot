/**
 * Dataset Ingestion & Profiling Frontend Controller
 */

let currentProfileData = null;
let currentFileName = null;

document.addEventListener("DOMContentLoaded", () => {
  initDropZone();
  loadDatasetsList();

  document.getElementById("btnIngest").addEventListener("click", handleIngest);
  document.getElementById("btnShowMarkdown").addEventListener("click", showMarkdownModal);
  document.getElementById("btnShowDdl").addEventListener("click", showDdlModal);
});

function initDropZone() {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");

  dropZone.addEventListener("click", () => fileInput.click());

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("dragover");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      uploadFile(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      uploadFile(e.target.files[0]);
    }
  });
}

async function uploadFile(file) {
  const dropZone = document.getElementById("dropZone");
  const origHtml = dropZone.innerHTML;
  dropZone.innerHTML = `<div style="font-size: 16px; font-weight: 600;">⏳ Uploading '${file.name}'...</div>`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/v1/datasets/upload", {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (res.ok) {
      alert(`✅ File '${file.name}' uploaded successfully!`);
      await loadDatasetsList();
      profileDataset(file.name);
    } else {
      alert(`❌ Upload failed: ${data.detail || data.error}`);
    }
  } catch (err) {
    alert(`❌ Upload error: ${err.message}`);
  } finally {
    dropZone.innerHTML = origHtml;
  }
}

async function loadDatasetsList() {
  const grid = document.getElementById("fileGrid");
  try {
    const res = await fetch("/api/v1/datasets");
    const data = await res.json();
    const files = data.datasets || [];

    if (files.length === 0) {
      grid.innerHTML = `<div style="color: #64748b; grid-column: 1/-1;">No datasets found in repository. Drop an Excel or CSV file above to start.</div>`;
      return;
    }

    grid.innerHTML = files.map(f => {
      const sizeMb = (f.file_size_bytes / (1024 * 1024)).toFixed(2);
      const isExcel = f.file_name.endsWith(".xlsx") || f.file_name.endsWith(".xls");
      const icon = isExcel ? "📗" : "📄";

      return `
        <div class="file-card">
          <div>
            <div class="file-title"><span>${icon}</span> <span>${f.file_name}</span></div>
            <div class="file-meta">Size: ${sizeMb} MB | ${f.directory}</div>
          </div>
          <div style="display: flex; gap: 8px;">
            <button class="nav-btn active" style="flex: 1; cursor: pointer; text-align: center;" onclick="profileDataset('${f.file_name}')">
              🔍 Profile Data
            </button>
          </div>
        </div>
      `;
    }).join("");

  } catch (err) {
    grid.innerHTML = `<div style="color: #ef4444; grid-column: 1/-1;">Failed to load dataset files: ${err.message}</div>`;
  }
}

async function profileDataset(fileName) {
  const profileSection = document.getElementById("profileSection");
  profileSection.style.display = "block";
  document.getElementById("profileTitle").innerText = `🔍 Profiling '${fileName}'...`;
  document.getElementById("profileSubtitle").innerText = "Analyzing column types, distinct categories, date patterns, and statistical distributions...";
  document.getElementById("profileTableBody").innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 24px; color: #94a3b8;">⏳ Running deep semantic profiling...</td></tr>`;
  
  profileSection.scrollIntoView({ behavior: "smooth" });

  try {
    const res = await fetch("/api/v1/datasets/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_name: fileName, sample_size: 5000 })
    });
    const data = await res.json();

    if (!res.ok) {
      alert(`❌ Profiling failed: ${data.detail || data.error}`);
      profileSection.style.display = "none";
      return;
    }

    currentProfileData = data;
    currentFileName = fileName;

    const table = data.tables[0];
    document.getElementById("profileTitle").innerText = `📊 ${table.table_name}`;
    document.getElementById("profileSubtitle").innerText = `${table.total_rows.toLocaleString()} rows | ${table.total_columns} columns | Clean Name: ${table.clean_table_name}`;
    document.getElementById("targetTableName").value = table.clean_table_name;

    renderProfileTable(table.columns);

  } catch (err) {
    alert(`❌ Profiling error: ${err.message}`);
    profileSection.style.display = "none";
  }
}

function renderProfileTable(columns) {
  const tbody = document.getElementById("profileTableBody");
  tbody.innerHTML = columns.map((col, idx) => {
    let typeClass = "type-empty";
    const t = col.inferred_type.toLowerCase();
    if (t.includes("date") || t.includes("time")) typeClass = "type-date";
    else if (t.includes("currency") || t.includes("percentage") || t.includes("float")) typeClass = "type-currency";
    else if (t.includes("identifier")) typeClass = "type-identifier";
    else if (t.includes("categorical") || t.includes("string")) typeClass = "type-categorical";
    else if (t.includes("boolean")) typeClass = "type-boolean";
    else if (t.includes("coordinate")) typeClass = "type-coordinate";

    const samples = col.distinct_values ? col.distinct_values.slice(0, 3).join(", ") : (col.sample_values ? col.sample_values.slice(0, 3).join(", ") : "-");

    return `
      <tr>
        <td style="color: #64748b;">${idx + 1}</td>
        <td>
          <div style="font-weight: 600;">${col.name}</div>
          <div style="font-size: 11px; color: #64748b;">sql: <code>${col.clean_name}</code></div>
        </td>
        <td><span class="type-badge ${typeClass}">${col.inferred_type}</span></td>
        <td><code>${col.sql_type}</code></td>
        <td style="color: #94a3b8;">${col.semantic_role}</td>
        <td>${col.null_percentage}%</td>
        <td style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${samples}">${samples}</td>
        <td style="font-size: 12px; color: #94a3b8; max-width: 300px;">${col.llm_guidance}</td>
      </tr>
    `;
  }).join("");
}

async function handleIngest() {
  if (!currentFileName) return;
  const targetTable = document.getElementById("targetTableName").value.trim();
  if (!targetTable) {
    alert("Please enter a valid target table name.");
    return;
  }

  const btn = document.getElementById("btnIngest");
  const origText = btn.innerText;
  btn.innerText = "⏳ Ingesting...";
  btn.disabled = true;

  try {
    const res = await fetch("/api/v1/datasets/ingest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file_name: currentFileName, table_name: targetTable })
    });
    const data = await res.json();

    if (res.ok) {
      if (confirm(`🎉 ${data.message}\n\nWould you like to open the AI Chatbot to start querying table '${data.table_name}' now?`)) {
        window.location.href = "/";
      }
    } else {
      alert(`❌ Ingestion failed: ${data.detail || data.error}`);
    }
  } catch (err) {
    alert(`❌ Ingestion error: ${err.message}`);
  } finally {
    btn.innerText = origText;
    btn.disabled = false;
  }
}

function showMarkdownModal() {
  if (!currentProfileData) return;
  const w = window.open("", "_blank");
  w.document.write(`<pre style="background: #0f172a; color: #e2e8f0; padding: 20px; font-family: monospace; white-space: pre-wrap;">${currentProfileData.llm_markdown}</pre>`);
}

function showDdlModal() {
  if (!currentProfileData) return;
  const w = window.open("", "_blank");
  w.document.write(`<pre style="background: #0f172a; color: #e2e8f0; padding: 20px; font-family: monospace; white-space: pre-wrap;">${currentProfileData.sql_ddl}</pre>`);
}
