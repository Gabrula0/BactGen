let samplesList = [];
let activeSampleId = null;
let stagedFastqFiles = [];
let stagedRefFile = null;

window.addEventListener("dragover", function (e) { e.preventDefault(); });
window.addEventListener("drop", function (e) { e.preventDefault(); });

function notify(text, isError) {
  const wrap = document.getElementById("toast");
  const msg = document.getElementById("toast-msg");
  msg.textContent = text;
  msg.className = isError
    ? "px-4 py-3 rounded-lg text-sm font-medium border bg-rose-100 text-rose-900 border-rose-300 shadow-sm"
    : "px-4 py-3 rounded-lg text-sm font-medium border bg-emerald-100 text-emerald-950 border-emerald-300 shadow-sm";
  wrap.classList.remove("hidden");
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(function () { wrap.classList.add("hidden"); }, 6000);
}

async function api(url, opts) {
  const res = await fetch(url, opts || {});
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch (e) {
    data = { detail: text || ("HTTP " + res.status) };
  }
  if (!res.ok) {
    const msg = Array.isArray(data.detail)
      ? data.detail.map(function (d) { return d.msg || JSON.stringify(d); }).join("; ")
      : (data.detail || ("HTTP " + res.status));
    throw new Error(msg);
  }
  return data;
}

function toggleAddDrawer(forceOpen) {
  const drawer = document.getElementById("add-sample-drawer");
  const icon = document.getElementById("drawer-icon");
  const shouldOpen = typeof forceOpen === "boolean" ? forceOpen : drawer.classList.contains("hidden");
  drawer.classList.toggle("hidden", !shouldOpen);
  icon.textContent = shouldOpen ? "-" : "+";
  if (shouldOpen) loadDiskFastqs();
}

function setFastqMode(mode) {
  const isDrop = mode === "drop";
  document.getElementById("fastq-drop-panel").classList.toggle("hidden", !isDrop);
  document.getElementById("fastq-disk-panel").classList.toggle("hidden", isDrop);
  document.getElementById("mode-drop").className = isDrop
    ? "flex-1 py-1.5 rounded-md font-semibold bg-pink-100/80 text-fuchsia-950 border border-pink-300"
    : "flex-1 py-1.5 rounded-md font-semibold bg-white text-slate-600 border border-pink-200";
  document.getElementById("mode-disk").className = !isDrop
    ? "flex-1 py-1.5 rounded-md font-semibold bg-pink-100/80 text-fuchsia-950 border border-pink-300"
    : "flex-1 py-1.5 rounded-md font-semibold bg-white text-slate-600 border border-pink-200";
  if (!isDrop) loadDiskFastqs();
}

function setRefMode(mode) {
  const isServer = mode === "server";
  document.getElementById("ref-server-panel").classList.toggle("hidden", !isServer);
  document.getElementById("ref-upload-panel").classList.toggle("hidden", isServer);
  document.getElementById("ref-mode-server").className = isServer
    ? "px-2.5 py-0.5 rounded bg-pink-100 text-fuchsia-950 font-semibold border border-pink-300"
    : "px-2.5 py-0.5 rounded bg-white text-slate-600 border border-pink-200";
  document.getElementById("ref-mode-upload").className = !isServer
    ? "px-2.5 py-0.5 rounded bg-pink-100 text-fuchsia-950 font-semibold border border-pink-300"
    : "px-2.5 py-0.5 rounded bg-white text-slate-600 border border-pink-200";
}

function clearSampleForm() {
  document.getElementById("f-sample-id").value = "";
  document.getElementById("f-source").value = "";
  document.getElementById("f-ward").value = "";
}

async function checkDatabase() {
  const badge = document.getElementById("header-badge");
  try {
    const data = await api("/health");
    badge.textContent = "Online: " + data.database;
    badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/20 text-emerald-200 border border-emerald-400/30";
  } catch (err) {
    badge.textContent = "Offline";
    badge.className = "px-3 py-1 rounded-full text-xs font-semibold bg-rose-500/20 text-rose-200 border border-rose-400/30";
  }
}

async function selectSample(sampleId) {
  activeSampleId = sampleId;
  document.getElementById("selected-sample-label").textContent = sampleId ? "Active sample: " + sampleId : "Active sample: None";
  document.getElementById("step2-target-badge").textContent = "Target: " + (sampleId || "None");
  renderSamplesTable();
  await loadLinkedRuns();
}

function renderSamplesTable() {
  const tbody = document.getElementById("samples-tbody");
  const counter = document.getElementById("sample-count");
  const total = samplesList.length;
  counter.textContent = total + (total === 1 ? " sample" : " samples");

  if (!total) {
    tbody.innerHTML =
      '<tr><td colspan="6" class="px-5 py-6 text-center text-xs opacity-60">' +
      "No samples in database yet. Click '+ Add a Sample & Sequencing Run' below to register one." +
      "</td></tr>";
    return;
  }

  tbody.innerHTML = samplesList.map(function (s) {
    const isSelected = s.sample_id === activeSampleId;
    const rowClass = isSelected ? "sample-row-active" : "hover:bg-pink-50/50 cursor-pointer";
    const btnClass = isSelected
      ? "px-3 py-1 rounded-md text-xs font-bold btn-plum"
      : "px-3 py-1 rounded-md text-xs font-semibold bg-white border border-pink-300 hover:bg-pink-50";
    const btnText = isSelected ? "Selected" : "Select";

    return (
      '<tr data-id="' + s.sample_id + '" class="' + rowClass + '">' +
      '<td class="px-5 py-3 font-mono font-bold text-xs">' + s.sample_id + "</td>" +
      '<td class="px-5 py-3 text-xs italic">' + s.organism + "</td>" +
      '<td class="px-5 py-3 text-xs">' + (s.hospital_ward || "-") + "</td>" +
      '<td class="px-5 py-3 text-xs">' + (s.sample_source || "-") + "</td>" +
      '<td class="px-5 py-3 text-xs">' + (s.collection_date || "-") + "</td>" +
      '<td class="px-5 py-3 text-right"><button type="button" class="' + btnClass + '">' + btnText + "</button></td>" +
      "</tr>"
    );
  }).join("");
}

async function loadSamples(preferredId) {
  try {
    samplesList = await api("/samples");
    if (samplesList.length > 0) {
      let target = samplesList[0].sample_id;
      if (preferredId && samplesList.some(function (s) { return s.sample_id === preferredId; })) {
        target = preferredId;
      } else if (activeSampleId && samplesList.some(function (s) { return s.sample_id === activeSampleId; })) {
        target = activeSampleId;
      }
      await selectSample(target);
    } else {
      await selectSample(null);
    }
  } catch (err) {
    samplesList = [];
    renderSamplesTable();
  }
}

async function loadLinkedRuns() {
  const container = document.getElementById("linked-runs-list");
  const runSel = document.getElementById("analysis-run-select");
  if (!activeSampleId) {
    container.innerHTML = '<span class="opacity-60">Select or register a sample to view its sequencing runs.</span>';
    if (runSel) runSel.innerHTML = '<option value="">Select a sample first</option>';
    return;
  }
  try {
    const runs = await api("/samples/" + encodeURIComponent(activeSampleId) + "/sequencing-runs");
    if (!runs.length) {
      container.innerHTML = '<span class="opacity-60">No sequencing runs linked to ' + activeSampleId + ' yet.</span>';
      if (runSel) runSel.innerHTML = '<option value="">No sequencing runs linked to ' + activeSampleId + " yet</option>";
      return;
    }
    container.innerHTML = runs.map(function (r) {
      const r1Name = r.fastq_r1_path.split("/").pop();
      const r2Name = r.fastq_r2_path ? " + " + r.fastq_r2_path.split("/").pop() : " (single-end)";
      return (
        '<div class="bg-pink-50/70 border border-pink-200 rounded-lg px-3 py-2 flex justify-between items-center">' +
        '<span class="font-mono font-semibold text-fuchsia-950">Run #' + r.run_id + ": " + r1Name + r2Name + "</span>" +
        '<span class="text-[11px] opacity-65 font-mono">MD5: ' + r.fastq_r1_md5.slice(0, 8) + "...</span>" +
        "</div>"
      );
    }).join("");
    if (runSel) {
      runSel.innerHTML = runs.map(function (r) {
        const name = r.fastq_r1_path.split("/").pop();
        return '<option value="' + r.run_id + '">Run #' + r.run_id + " - " + name + "</option>";
      }).join("");
    }
  } catch (err) {
    container.innerHTML = '<span class="text-rose-700">Could not load runs.</span>';
  }
}

async function loadDiskFastqs() {
  try {
    const files = await api("/samples/available-fastq");
    const opts = files.map(function (f) { return '<option value="' + f + '">' + f + "</option>"; }).join("");
    document.getElementById("disk-r1-select").innerHTML = opts || '<option value="">No FASTQ files in data/fastq/</option>';
    document.getElementById("disk-r2-select").innerHTML = '<option value="">-- None (Single-end) --</option>' + opts;
  } catch (err) {}
}

async function loadServerReferences(preferredPath) {
  try {
    const refs = await api("/analyses/available-references");
    const sel = document.getElementById("ref-server-select");
    if (!sel) return;
    if (!refs.length) {
      sel.innerHTML = '<option value="">No FASTA in data/reference/ (use Upload FASTA)</option>';
      return;
    }
    sel.innerHTML = refs.map(function (r) {
      return '<option value="' + r + '">' + r + "</option>";
    }).join("");
    if (preferredPath && refs.includes(preferredPath)) {
      sel.value = preferredPath;
    }
  } catch (err) {}
}

document.getElementById("sample-form").addEventListener("submit", async function (e) {
  e.preventDefault();
  const payload = {
    sample_id: document.getElementById("f-sample-id").value.trim(),
    organism: document.getElementById("f-organism").value.trim(),
    collection_date: document.getElementById("f-date").value,
    sample_source: document.getElementById("f-source").value.trim() || null,
    hospital_ward: document.getElementById("f-ward").value.trim() || null
  };
  const btn = document.getElementById("save-sample-btn");
  btn.disabled = true;
  btn.textContent = "Saving...";
  try {
    await api("/samples", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    notify("Sample " + payload.sample_id + " saved! Now attach FASTQ reads in Step 2.", false);
    await loadSamples(payload.sample_id);
  } catch (err) {
    notify(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Save Sample Metadata";
  }
});

function stageFastqFiles(files) {
  let list = stagedFastqFiles.slice();
  for (let i = 0; i < files.length; i++) {
    const f = files[i];
    if (!list.some(function (x) { return x.name === f.name; })) list.push(f);
  }
  list = list.slice(0, 2).sort(function (a, b) {
    const aR2 = /(_R?2)(\.|_|$)/i.test(a.name);
    const bR2 = /(_R?2)(\.|_|$)/i.test(b.name);
    if (aR2 !== bR2) return aR2 ? 1 : -1;
    return a.name.localeCompare(b.name);
  });
  stagedFastqFiles = list;
  renderStagedFastq();
}

function swapR1R2() {
  if (stagedFastqFiles.length === 2) {
    stagedFastqFiles = [stagedFastqFiles[1], stagedFastqFiles[0]];
    renderStagedFastq();
  }
}

function clearFastqFiles() {
  stagedFastqFiles = [];
  document.getElementById("fastq-input").value = "";
  renderStagedFastq();
}

function renderStagedFastq() {
  const box = document.getElementById("fastq-staged-box");
  const list = document.getElementById("fastq-staged-list");
  const swapBtn = document.getElementById("swap-r1r2-btn");
  if (!stagedFastqFiles.length) {
    box.classList.add("hidden");
    list.innerHTML = "";
    return;
  }
  box.classList.remove("hidden");
  swapBtn.classList.toggle("hidden", stagedFastqFiles.length < 2);
  list.innerHTML = stagedFastqFiles.map(function (f, idx) {
    const role = idx === 0 ? "R1" : "R2";
    const mb = (f.size / 1048576).toFixed(1);
    return (
      '<div class="text-xs font-mono text-fuchsia-950 bg-white px-2.5 py-1.5 rounded border border-pink-200 flex justify-between items-center">' +
      "<span><strong>" + role + ":</strong> " + f.name + "</span>" +
      '<span class="opacity-60">' + mb + " MB</span></div>"
    );
  }).join("");
}

async function submitFastqUpload() {
  if (!activeSampleId) return notify("Register or select a sample first before linking FASTQ files.", true);
  if (!stagedFastqFiles.length) return notify("Drop or select at least the R1 (.fastq.gz) file first.", true);
  const btn = document.getElementById("upload-fastq-btn");
  btn.disabled = true;
  btn.textContent = "Uploading & creating Sequencing Run...";
  try {
    const fd = new FormData();
    fd.append("r1_file", stagedFastqFiles[0]);
    if (stagedFastqFiles[1]) fd.append("r2_file", stagedFastqFiles[1]);
    const url = "/samples/" + encodeURIComponent(activeSampleId) + "/sequencing-runs/upload";
    const run = await api(url, { method: "POST", body: fd });
    notify("Sequencing Run #" + run.run_id + " created and linked to " + activeSampleId + "!", false);
    clearFastqFiles();
    await loadLinkedRuns();
    await loadDiskFastqs();
  } catch (err) {
    notify(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload FASTQ & Create Sequencing Run";
  }
}

async function submitDiskFastq() {
  if (!activeSampleId) return notify("Register or select a sample first.", true);
  const r1 = document.getElementById("disk-r1-select").value;
  const r2 = document.getElementById("disk-r2-select").value || null;
  if (!r1) return notify("Select a FASTQ R1 file from data/fastq/.", true);
  try {
    const url = "/samples/" + encodeURIComponent(activeSampleId) + "/sequencing-runs";
    const run = await api(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fastq_r1_path: r1, fastq_r2_path: r2 })
    });
    notify("Sequencing Run #" + run.run_id + " linked to " + activeSampleId + "!", false);
    await loadLinkedRuns();
  } catch (err) {
    notify(err.message, true);
  }
}

function stageRefFile(file) {
  stagedRefFile = file;
  document.getElementById("ref-staged-label").textContent = "Selected: " + file.name;
}

async function submitReferenceUpload() {
  if (!stagedRefFile) return notify("Select or drop a FASTA file (.fasta, .fa, .fna) first.", true);
  const btn = document.getElementById("upload-ref-btn");
  btn.disabled = true;
  btn.textContent = "Uploading FASTA...";
  try {
    const fd = new FormData();
    fd.append("fasta_file", stagedRefFile);
    const res = await api("/analyses/upload-reference", { method: "POST", body: fd });
    notify("Reference FASTA uploaded: " + res.filename, false);
    stagedRefFile = null;
    document.getElementById("ref-file-input").value = "";
    document.getElementById("ref-staged-label").textContent = "";
    await loadServerReferences(res.reference_path);
    setRefMode("server");
  } catch (err) {
    notify(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Upload Reference FASTA";
  }
}

async function submitAnalysis() {
  const runId = Number(document.getElementById("analysis-run-select").value);
  const refPath = document.getElementById("ref-server-select").value;
  if (!runId) return notify("Link a FASTQ Sequencing Run to the active sample first.", true);
  if (!refPath) return notify("Select or upload a FASTA reference genome first.", true);

  const btn = document.getElementById("launch-analysis-btn");
  btn.disabled = true;
  btn.textContent = "Queuing analysis...";
  try {
    const res = await api("/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, reference_path: refPath })
    });
    notify("Analysis #" + res.analysis_id + " queued (" + res.status + ") for " + activeSampleId + "!", false);
  } catch (err) {
    notify(err.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Launch Analysis";
  }
}

const dropzone = document.getElementById("fastq-dropzone");
dropzone.addEventListener("dragover", function (e) { e.preventDefault(); e.stopPropagation(); dropzone.classList.add("drag-active"); });
dropzone.addEventListener("dragleave", function (e) { e.preventDefault(); e.stopPropagation(); dropzone.classList.remove("drag-active"); });
dropzone.addEventListener("drop", function (e) {
  e.preventDefault();
  e.stopPropagation();
  dropzone.classList.remove("drag-active");
  if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) stageFastqFiles(Array.from(e.dataTransfer.files));
});

const refZone = document.getElementById("ref-dropzone");
if (refZone) {
  refZone.addEventListener("dragover", function (e) { e.preventDefault(); e.stopPropagation(); refZone.classList.add("drag-active"); });
  refZone.addEventListener("dragleave", function (e) { e.preventDefault(); e.stopPropagation(); refZone.classList.remove("drag-active"); });
  refZone.addEventListener("drop", function (e) {
    e.preventDefault();
    e.stopPropagation();
    refZone.classList.remove("drag-active");
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) stageRefFile(e.dataTransfer.files[0]);
  });
}

document.getElementById("fastq-input").addEventListener("change", function (e) {
  if (e.target.files && e.target.files.length) stageFastqFiles(Array.from(e.target.files));
});

const refInput = document.getElementById("ref-file-input");
if (refInput) {
  refInput.addEventListener("change", function (e) {
    if (e.target.files && e.target.files[0]) stageRefFile(e.target.files[0]);
  });
}

document.getElementById("samples-tbody").addEventListener("click", function (e) {
  const row = e.target.closest("tr[data-id]");
  if (row) selectSample(row.getAttribute("data-id"));
});

checkDatabase();
loadSamples(null);
loadServerReferences(null);

const expandedSamples = new Set();
let detailsPollTimer = null;

function statusBadgeHtml(status) {
  const colors = {
    SUCCESS: "bg-emerald-100 text-emerald-800 border-emerald-300",
    RUNNING: "bg-amber-100 text-amber-800 border-amber-300 animate-pulse",
    QUEUED: "bg-indigo-100 text-indigo-800 border-indigo-300",
    FAILED: "bg-rose-100 text-rose-800 border-rose-300"
  };
  const cls = colors[status] || "bg-slate-100 text-slate-800 border-slate-300";
  return '<span class="px-2 py-0.5 rounded-full text-[11px] font-bold border ' + cls + '">' + status + "</span>";
}

renderSamplesTable = function () {
  const tbody = document.getElementById("samples-tbody");
  const counter = document.getElementById("sample-count");
  const total = samplesList.length;
  counter.textContent = total + (total === 1 ? " sample" : " samples");

  if (!total) {
    tbody.innerHTML =
      '<tr><td colspan="6" class="px-5 py-6 text-center text-xs opacity-60">' +
      "No samples in database yet. Click Add a Sample below to register one." +
      "</td></tr>";
    return;
  }

  tbody.innerHTML = samplesList.map(function (s) {
    const id = s.sample_id;
    const isSelected = id === activeSampleId;
    const isOpen = expandedSamples.has(id);
    const rowCls = isSelected ? "sample-row-active" : "hover:bg-pink-50/50 cursor-pointer";
    const selCls = isSelected
      ? "px-2.5 py-1 rounded-md text-xs font-bold btn-plum"
      : "px-2.5 py-1 rounded-md text-xs font-semibold bg-white border border-pink-300 hover:bg-pink-50";
    const expCls = isOpen
      ? "px-2.5 py-1 rounded-md text-xs font-semibold bg-fuchsia-100 text-fuchsia-950 border border-fuchsia-300"
      : "px-2.5 py-1 rounded-md text-xs font-semibold bg-pink-50 text-fuchsia-900 border border-pink-200 hover:bg-pink-100";
    const expLabel = isOpen ? "Hide Runs" : "Runs & Analyses";

    const mainRow =
      '<tr data-id="' + id + '" class="' + rowCls + '">' +
      '<td class="px-5 py-3 font-mono font-bold text-xs">' + id + "</td>" +
      '<td class="px-5 py-3 text-xs italic">' + s.organism + "</td>" +
      '<td class="px-5 py-3 text-xs">' + (s.hospital_ward || "-") + "</td>" +
      '<td class="px-5 py-3 text-xs">' + (s.sample_source || "-") + "</td>" +
      '<td class="px-5 py-3 text-xs">' + (s.collection_date || "-") + "</td>" +
      '<td class="px-5 py-3 text-right space-x-1.5 whitespace-nowrap">' +
      '<button type="button" data-toggle-details="' + id + '" class="' + expCls + '">' + expLabel + "</button>" +
      '<button type="button" class="' + selCls + '">' + (isSelected ? "Selected" : "Select") + "</button>" +
      "</td></tr>";

    const subRow = isOpen
      ? '<tr class="bg-pink-50/40"><td colspan="6" id="details-box-' + id + '" class="px-6 py-4 border-t border-pink-100">' +
        '<span class="text-xs opacity-65">Loading sequencing runs and analyses...</span></td></tr>'
      : "";

    return mainRow + subRow;
  }).join("");

  expandedSamples.forEach(function (id) {
    loadSampleDetailsPanel(id);
  });
};

async function loadSampleDetailsPanel(sampleId) {
  const box = document.getElementById("details-box-" + sampleId);
  if (!box) return;

  try {
    const pair = await Promise.all([
      api("/samples/" + encodeURIComponent(sampleId) + "/sequencing-runs"),
      api("/analyses")
    ]);
    const runs = pair[0];
    const sampleAnalyses = pair[1].filter(function (a) {
      return a.sample_id === sampleId;
    });

    if (!runs.length) {
      box.innerHTML =
        '<div class="flex items-center justify-between text-xs bg-white rounded-xl border border-pink-200 px-4 py-3">' +
        '<span class="opacity-70">No sequencing runs linked to <strong>' + sampleId + "</strong> yet.</span>" +
        '<button type="button" data-refresh-details="' + sampleId + '" class="underline text-fuchsia-900 font-semibold">Refresh</button>' +
        "</div>";
      return;
    }

    const runsHtml = runs.map(function (run) {
      const r1 = run.fastq_r1_path.split("/").pop();
      const r2 = run.fastq_r2_path ? run.fastq_r2_path.split("/").pop() : "";
      const linkedAnalyses = sampleAnalyses.filter(function (a) {
        return a.run_id !== undefined ? a.run_id === run.run_id : true;
      });

      const analysesBlock = linkedAnalyses.length
        ? '<div class="mt-2.5 pt-2.5 border-t border-pink-100 space-y-1.5">' +
          '<div class="text-[11px] font-bold uppercase opacity-60">Analyses (' + linkedAnalyses.length + ")</div>" +
          linkedAnalyses.map(function (a) {
            const refName = (a.reference_genome || "").split("/").pop();
            const errMsg = a.status === "FAILED" && a.error_message
              ? '<span class="text-[11px] text-rose-700 ml-2">' + a.error_message + "</span>"
              : "";
            return (
              '<div class="flex flex-wrap items-center justify-between gap-2 bg-pink-50/70 rounded-lg px-3 py-1.5 text-xs">' +
              '<div><span class="font-mono font-bold text-fuchsia-950">Analysis #' + a.analysis_id + "</span>" +
              '<span class="font-mono text-[11px] opacity-75 ml-2">Ref: ' + refName + "</span>" + errMsg + "</div>" +
              "<div>" + statusBadgeHtml(a.status) + "</div></div>"
            );
          }).join("") + "</div>"
        : '<div class="mt-2 pt-2 border-t border-pink-100 text-[11px] opacity-60">No analyses executed for this sequencing run yet.</div>';

      return (
        '<div class="bg-white rounded-xl border border-pink-200 p-3.5 shadow-sm">' +
        '<div class="flex flex-wrap items-center justify-between gap-2 text-xs font-mono">' +
        '<div><span class="font-bold text-fuchsia-950">Sequencing Run #' + run.run_id + "</span>" +
        '<span class="ml-2 px-2 py-0.5 rounded bg-pink-100/80 text-fuchsia-950 font-semibold">R1: ' + r1 + "</span>" +
        (r2 ? '<span class="ml-1.5 px-2 py-0.5 rounded bg-purple-100/80 text-purple-950 font-semibold">R2: ' + r2 + "</span>" : "") +
        "</div>" +
        '<span class="text-[11px] opacity-60">MD5: ' + (run.fastq_r1_md5 || "").slice(0, 10) + "...</span>" +
        "</div>" + analysesBlock + "</div>"
      );
    }).join("");

    box.innerHTML =
      '<div class="space-y-2.5">' +
      '<div class="flex items-center justify-between">' +
      '<span class="text-xs font-bold uppercase tracking-wider text-fuchsia-900">Sequencing Runs & Analyses for ' + sampleId + "</span>" +
      '<button type="button" data-refresh-details="' + sampleId + '" class="text-[11px] font-semibold text-fuchsia-900 underline">Refresh</button>' +
      "</div>" + runsHtml + "</div>";

    clearTimeout(detailsPollTimer);
    if (sampleAnalyses.some(function (a) { return a.status === "QUEUED" || a.status === "RUNNING"; })) {
      detailsPollTimer = setTimeout(function () {
        expandedSamples.forEach(function (id) { loadSampleDetailsPanel(id); });
      }, 4000);
    }
  } catch (err) {
    box.innerHTML = '<div class="text-xs text-rose-700">Error loading details: ' + err.message + "</div>";
  }
}

document.getElementById("samples-tbody").addEventListener("click", function (e) {
  const toggleBtn = e.target.closest("[data-toggle-details]");
  if (toggleBtn) {
    e.stopPropagation();
    const id = toggleBtn.getAttribute("data-toggle-details");
    if (expandedSamples.has(id)) {
      expandedSamples.delete(id);
    } else {
      expandedSamples.add(id);
    }
    renderSamplesTable();
    return;
  }
  const refreshBtn = e.target.closest("[data-refresh-details]");
  if (refreshBtn) {
    e.stopPropagation();
    loadSampleDetailsPanel(refreshBtn.getAttribute("data-refresh-details"));
  }
}, true);

function closeResultsPanel() {
  document.getElementById("genomic-results-panel").classList.add("hidden");
}

function fmtNum(val, suffix) {
  if (val === null || val === undefined) return "-";
  return Number(val).toLocaleString() + (suffix || "");
}

function fmtPct(val, isFraction) {
  if (val === null || val === undefined) return "-";
  const num = isFraction && val <= 1 ? val * 100 : Number(val);
  return num.toFixed(1) + "%";
}

async function openAnalysisResults(analysisId, sampleId) {
  const panel = document.getElementById("genomic-results-panel");
  const title = document.getElementById("results-title");
  const qcBadge = document.getElementById("results-qc-badge");
  const kpis = document.getElementById("results-kpis");
  const mlstSt = document.getElementById("results-mlst-st");
  const mlstAlleles = document.getElementById("results-mlst-alleles");
  const pathsBox = document.getElementById("results-paths");
  const amrBox = document.getElementById("results-amr-box");

  panel.classList.remove("hidden");
  title.textContent = "Loading Analysis #" + analysisId + (sampleId ? " (" + sampleId + ")" : "") + "...";
  kpis.innerHTML = "";
  amrBox.innerHTML = '<div class="text-xs opacity-65">Loading genomic results...</div>';
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });

  try {
    const r = await api("/analyses/" + analysisId + "/results");
    title.textContent = "Analysis #" + r.analysis_id + (sampleId ? " - Sample " + sampleId : "");

    const pass = (r.qc_status || "").toUpperCase() === "PASS";
    qcBadge.textContent = "QC: " + (r.qc_status || "UNKNOWN");
    qcBadge.className = pass
      ? "px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300"
      : "px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300";

    const cards = [
      { label: "Mean Depth", val: r.mean_depth != null ? r.mean_depth.toFixed(1) + "x" : "-" },
      { label: "Genome Coverage", val: fmtPct(r.genome_coverage_pct, false) },
      { label: "Mapped Reads", val: fmtPct(r.mapped_reads_pct, false) },
      { label: "Q30 Rate", val: fmtPct(r.q30_rate, true) },
      { label: "Clean / Raw Reads", val: fmtNum(r.clean_reads) + " / " + fmtNum(r.raw_reads) },
      { label: "Total SNPs", val: fmtNum(r.total_snps) },
      { label: "Total Indels", val: fmtNum(r.total_indels) },
      { label: "Result ID", val: "#" + r.result_id }
    ];

    kpis.innerHTML = cards.map(function (c) {
      return (
        '<div class="bg-pink-50/60 border border-pink-200 rounded-xl p-3">' +
        '<div class="text-[11px] uppercase opacity-65 font-semibold">' + c.label + "</div>" +
        '<div class="text-sm font-mono font-bold text-fuchsia-950 mt-0.5">' + c.val + "</div>" +
        "</div>"
      );
    }).join("");

    mlstSt.textContent = r.mlst ? "ST" + String(r.mlst).replace(/^ST/i, "") : "Untyped";
    const alleles = r.mlst_alleles || {};
    const alleleKeys = Object.keys(alleles);
    mlstAlleles.innerHTML = alleleKeys.length
      ? alleleKeys.map(function (k) {
          return '<span class="px-2 py-0.5 rounded bg-white border border-pink-200">' + k + ": <strong>" + alleles[k] + "</strong></span>";
        }).join("")
      : '<span class="opacity-60">No MLST allele breakdown recorded.</span>';

    pathsBox.innerHTML =
      "<div><strong>VCF:</strong> " + (r.vcf_path || "-") + "</div>" +
      "<div><strong>Consensus:</strong> " + (r.consensus_path || "-") + "</div>";

    const genes = Array.isArray(r.resistance_genes) ? r.resistance_genes : [];
    if (!genes.length) {
      amrBox.innerHTML = '<div class="text-xs opacity-65 bg-pink-50/50 border border-pink-200 rounded-lg px-3 py-2.5">No antimicrobial resistance genes detected.</div>';
    } else if (typeof genes[0] === "string") {
      amrBox.innerHTML = '<div class="flex flex-wrap gap-1.5">' + genes.map(function (g) {
        return '<span class="px-2.5 py-1 rounded-full text-xs font-mono font-bold bg-rose-100 text-rose-900 border border-rose-300">' + g + "</span>";
      }).join("") + "</div>";
    } else {
      amrBox.innerHTML =
        '<table class="w-full text-left text-xs border border-pink-200 rounded-lg overflow-hidden">' +
        '<thead class="bg-pink-50/80 uppercase opacity-70 border-b border-pink-200">' +
        '<tr><th class="px-3 py-2">Gene</th><th class="px-3 py-2">Resistance / Product</th><th class="px-3 py-2">Coverage</th><th class="px-3 py-2">Identity</th></tr></thead>' +
        '<tbody class="divide-y divide-pink-100">' +
        genes.map(function (g) {
          const name = g.gene || g.GENE || g.name || "-";
          const res = g.resistance || g.RESISTANCE || g.product || g.PRODUCT || "-";
          const cov = g.coverage != null ? g.coverage + "%" : (g["%COVERAGE"] ? g["%COVERAGE"] + "%" : "-");
          const idn = g.identity != null ? g.identity + "%" : (g["%IDENTITY"] ? g["%IDENTITY"] + "%" : "-");
          return (
            '<tr class="bg-white">' +
            '<td class="px-3 py-2 font-mono font-bold text-rose-900">' + name + "</td>" +
            '<td class="px-3 py-2">' + res + "</td>" +
            '<td class="px-3 py-2 font-mono">' + cov + "</td>" +
            '<td class="px-3 py-2 font-mono">' + idn + "</td>" +
            "</tr>"
          );
        }).join("") +
        "</tbody></table>";
    }
  } catch (err) {
    amrBox.innerHTML = '<div class="text-xs text-rose-700">' + err.message + "</div>";
  }
}

loadSampleDetailsPanel = async function (sampleId) {
  const box = document.getElementById("details-box-" + sampleId);
  if (!box) return;

  try {
    const pair = await Promise.all([
      api("/samples/" + encodeURIComponent(sampleId) + "/sequencing-runs"),
      api("/analyses")
    ]);
    const runs = pair[0];
    const sampleAnalyses = pair[1].filter(function (a) {
      return a.sample_id === sampleId;
    });

    if (!runs.length) {
      box.innerHTML =
        '<div class="flex items-center justify-between text-xs bg-white rounded-xl border border-pink-200 px-4 py-3">' +
        '<span class="opacity-70">No sequencing runs linked to <strong>' + sampleId + "</strong> yet.</span>" +
        '<button type="button" data-refresh-details="' + sampleId + '" class="underline text-fuchsia-900 font-semibold">Refresh</button>' +
        "</div>";
      return;
    }

    const runsHtml = runs.map(function (run) {
      const r1 = run.fastq_r1_path.split("/").pop();
      const r2 = run.fastq_r2_path ? run.fastq_r2_path.split("/").pop() : "";
      const linkedAnalyses = sampleAnalyses.filter(function (a) {
        return a.run_id !== undefined ? a.run_id === run.run_id : true;
      });

      const analysesBlock = linkedAnalyses.length
        ? '<div class="mt-2.5 pt-2.5 border-t border-pink-100 space-y-1.5">' +
          '<div class="text-[11px] font-bold uppercase opacity-60">Analyses (' + linkedAnalyses.length + ")</div>" +
          linkedAnalyses.map(function (a) {
            const refName = (a.reference_genome || "").split("/").pop();
            const errMsg = a.status === "FAILED" && a.error_message
              ? '<span class="text-[11px] text-rose-700 ml-2">' + a.error_message + "</span>"
              : "";
            const viewBtn = a.status === "SUCCESS"
              ? '<button type="button" data-view-results="' + a.analysis_id + '" data-sample-id="' + sampleId + '" ' +
                'class="px-2.5 py-0.5 rounded-md text-[11px] font-bold btn-plum">View Results</button>'
              : "";
            return (
              '<div class="flex flex-wrap items-center justify-between gap-2 bg-pink-50/70 rounded-lg px-3 py-1.5 text-xs">' +
              '<div><span class="font-mono font-bold text-fuchsia-950">Analysis #' + a.analysis_id + "</span>" +
              '<span class="font-mono text-[11px] opacity-75 ml-2">Ref: ' + refName + "</span>" + errMsg + "</div>" +
              '<div class="flex items-center gap-2">' + viewBtn + statusBadgeHtml(a.status) + "</div></div>"
            );
          }).join("") + "</div>"
        : '<div class="mt-2 pt-2 border-t border-pink-100 text-[11px] opacity-60">No analyses executed for this sequencing run yet.</div>';

      return (
        '<div class="bg-white rounded-xl border border-pink-200 p-3.5 shadow-sm">' +
        '<div class="flex flex-wrap items-center justify-between gap-2 text-xs font-mono">' +
        '<div><span class="font-bold text-fuchsia-950">Sequencing Run #' + run.run_id + "</span>" +
        '<span class="ml-2 px-2 py-0.5 rounded bg-pink-100/80 text-fuchsia-950 font-semibold">R1: ' + r1 + "</span>" +
        (r2 ? '<span class="ml-1.5 px-2 py-0.5 rounded bg-purple-100/80 text-purple-950 font-semibold">R2: ' + r2 + "</span>" : "") +
        "</div>" +
        '<span class="text-[11px] opacity-60">MD5: ' + (run.fastq_r1_md5 || "").slice(0, 10) + "...</span>" +
        "</div>" + analysesBlock + "</div>"
      );
    }).join("");

    box.innerHTML =
      '<div class="space-y-2.5">' +
      '<div class="flex items-center justify-between">' +
      '<span class="text-xs font-bold uppercase tracking-wider text-fuchsia-900">Sequencing Runs & Analyses for ' + sampleId + "</span>" +
      '<button type="button" data-refresh-details="' + sampleId + '" class="text-[11px] font-semibold text-fuchsia-900 underline">Refresh</button>' +
      "</div>" + runsHtml + "</div>";

    clearTimeout(detailsPollTimer);
    if (sampleAnalyses.some(function (a) { return a.status === "QUEUED" || a.status === "RUNNING"; })) {
      detailsPollTimer = setTimeout(function () {
        expandedSamples.forEach(function (id) { loadSampleDetailsPanel(id); });
      }, 4000);
    }
  } catch (err) {
    box.innerHTML = '<div class="text-xs text-rose-700">Error loading details: ' + err.message + "</div>";
  }
};

document.getElementById("samples-tbody").addEventListener("click", function (e) {
  const resBtn = e.target.closest("[data-view-results]");
  if (resBtn) {
    e.stopPropagation();
    openAnalysisResults(resBtn.getAttribute("data-view-results"), resBtn.getAttribute("data-sample-id"));
  }
}, true);

async function loadOutbreakSurveillance() {
  const input = document.getElementById("snp-threshold-input");
  const maxSnps = input ? Number(input.value || 20) : 20;
  const summary = document.getElementById("clusters-summary");
  const grid = document.getElementById("clusters-grid");
  const distCount = document.getElementById("distances-count");
  const distBody = document.getElementById("distances-tbody");

  try {
    const pair = await Promise.all([
      api("/clusters?max_snps=" + maxSnps),
      api("/outbreaks/distances?max_snps=" + maxSnps)
    ]);
    const clusterData = pair[0];
    const distances = pair[1];

    const clusters = clusterData.clusters || [];
    summary.textContent = clusters.length + (clusters.length === 1 ? " cluster" : " clusters") + " (<= " + maxSnps + " SNPs)";

    if (!clusters.length) {
      grid.innerHTML =
        '<div class="md:col-span-2 bg-pink-50/50 border border-pink-200 rounded-xl p-4 text-xs opacity-70">' +
        "No outbreak clusters detected within <= " + maxSnps + " SNPs. Try increasing the SNP threshold or running more samples against the same reference." +
        "</div>";
    } else {
      grid.innerHTML = clusters.map(function (c, idx) {
        const cid = c.cluster_id != null ? c.cluster_id : (idx + 1);
        const members = c.samples || c.sample_ids || [];
        const ref = (c.reference_genome || "").split("/").pop();
        const maxDist = c.max_snp_distance != null ? "Max " + c.max_snp_distance + " SNPs" : "";
        const badges = members.map(function (m) {
          return '<span class="px-2 py-0.5 rounded bg-white border border-pink-300 font-mono font-bold text-xs text-fuchsia-950">' + m + "</span>";
        }).join(" ");

        return (
          '<div class="bg-pink-50/60 border border-pink-200 rounded-xl p-4 space-y-2">' +
          '<div class="flex items-center justify-between text-xs">' +
          '<span class="font-bold text-fuchsia-950">Cluster #' + cid + " (" + members.length + " isolates)</span>" +
          '<span class="px-2 py-0.5 rounded-full bg-rose-100 text-rose-900 font-bold text-[11px]">' + (maxDist || "<= " + maxSnps + " SNPs") + "</span>" +
          "</div>" +
          '<div class="flex flex-wrap gap-1.5">' + badges + "</div>" +
          (ref ? '<div class="text-[11px] font-mono opacity-65">Ref: ' + ref + "</div>" : "") +
          "</div>"
        );
      }).join("");
    }

    distCount.textContent = distances.length + (distances.length === 1 ? " pair" : " pairs");
    if (!distances.length) {
      distBody.innerHTML =
        '<tr><td colspan="5" class="px-4 py-6 text-center opacity-60">' +
        "No pairwise SNP distances found within <= " + maxSnps + " SNPs." +
        "</td></tr>";
    } else {
      distBody.innerHTML = distances.map(function (d) {
        const ref = (d.reference_genome || "").split("/").pop();
        const snpBadge = d.snp_distance <= 5
          ? "bg-rose-100 text-rose-900 border-rose-300"
          : "bg-amber-100 text-amber-900 border-amber-300";
        return (
          '<tr class="hover:bg-pink-50/40">' +
          '<td class="px-4 py-2.5 font-mono font-bold">' + d.sample_a_id + "</td>" +
          '<td class="px-4 py-2.5 font-mono font-bold">' + d.sample_b_id + "</td>" +
          '<td class="px-4 py-2.5"><span class="px-2 py-0.5 rounded-full font-mono font-bold border ' + snpBadge + '">' + d.snp_distance + " SNPs</span></td>" +
          '<td class="px-4 py-2.5 font-mono opacity-75">' + d.shared_snps + "</td>" +
          '<td class="px-4 py-2.5 font-mono opacity-75">' + ref + "</td>" +
          "</tr>"
        );
      }).join("");
    }
  } catch (err) {
    summary.textContent = "Error";
    grid.innerHTML = '<div class="text-xs text-rose-700">' + err.message + "</div>";
  }
}

loadOutbreakSurveillance();
