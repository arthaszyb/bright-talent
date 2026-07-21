// DE Fleet Governance Console -- plain JS SPA, no build step, no CDN.
// Hash-based routing: #/fleet, #/instances/:id, #/drafts/:id, #/audit

const app = document.getElementById("app");

async function api(path, opts) {
  const res = await fetch(path, Object.assign({
    headers: { "Content-Type": "application/json" },
  }, opts || {}));
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = { raw: text }; }
  if (!res.ok) {
    const msg = (data && data.detail) ? data.detail : (res.statusText || "request failed");
    const err = new Error(msg);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

function h(tag, attrs, children) {
  const el = document.createElement(tag);
  attrs = attrs || {};
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v);
  }
  (children || []).forEach((c) => {
    if (c === null || c === undefined) return;
    el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  return el;
}

function fmtTime(t) {
  if (!t) return "-";
  try {
    if (typeof t === "number") return new Date(t * 1000).toLocaleString();
    return new Date(t + "Z").toLocaleString();
  } catch (e) { return String(t); }
}

// ---- Fleet view ------------------------------------------------------------

async function renderFleet() {
  app.innerHTML = "";
  app.appendChild(h("div", { class: "section" }, [
    h("h2", {}, ["Fleet Overview"]),
  ]));
  const loading = h("div", { class: "empty-state" }, ["Loading fleet..."]);
  app.appendChild(loading);

  let data;
  try {
    data = await api("/api/instances");
  } catch (e) {
    loading.textContent = "Failed to load: " + e.message;
    return;
  }
  loading.remove();

  const grid = h("div", { class: "grid" });
  if (!data.instances.length) {
    grid.appendChild(h("div", { class: "empty-state" }, ["No instances found under instances/."]));
  }
  data.instances.forEach((inst) => {
    const health = inst.health;
    const card = h("div", { class: "card clickable", onclick: () => { location.hash = "#/instances/" + inst.instance_id; } }, [
      h("div", { class: "card-header" }, [
        h("h3", {}, [inst.instance_id]),
        h("div", { class: "score-ring " + health.color }, [String(health.score)]),
      ]),
      h("div", {}, [h("span", { class: "badge " + health.status }, [health.status])]),
      h("div", { class: "muted", style: "margin-top:8px" }, [
        (inst.identity && inst.identity.description) || "",
      ]),
      h("div", { class: "muted", style: "margin-top:10px" }, [
        `base ${inst.base.built_scaffold_version || "?"} (current ${inst.base.current_scaffold_version || "?"}) · CI ${inst.ci.available ? "available" : "unavailable"} · ${inst.skills.length} skill(s)`,
      ]),
    ]);
    grid.appendChild(card);
  });
  app.appendChild(grid);
}

// ---- Instance detail --------------------------------------------------------

async function renderInstance(instanceId) {
  app.innerHTML = "";
  app.appendChild(h("a", { class: "back-link", href: "#/fleet" }, ["← back to fleet"]));
  const loading = h("div", { class: "empty-state" }, ["Loading " + instanceId + "..."]);
  app.appendChild(loading);

  let inst, draftsResp;
  try {
    inst = await api("/api/instances/" + encodeURIComponent(instanceId));
    draftsResp = await api("/api/drafts?instance_id=" + encodeURIComponent(instanceId));
  } catch (e) {
    loading.textContent = "Failed to load: " + e.message;
    return;
  }
  loading.remove();

  const health = inst.health;
  app.appendChild(h("div", { class: "section" }, [
    h("div", { class: "card-header" }, [
      h("h2", { style: "margin:0" }, [inst.instance_id]),
      h("div", { class: "score-ring " + health.color }, [String(health.score)]),
    ]),
    h("div", {}, [
      h("span", { class: "badge " + health.status }, [health.status]),
      h("span", { class: "muted", style: "margin-left:10px" }, [health.label]),
    ]),
  ]));

  // Health deductions
  app.appendChild(h("div", { class: "section" }, [
    h("h2", {}, ["Health"]),
    h("div", { class: "card" }, [
      health.deductions.length
        ? h("table", {}, [
            h("thead", {}, [h("tr", {}, [h("th", {}, ["Reason"]), h("th", {}, ["Points"])])]),
            h("tbody", {}, health.deductions.map((d) => h("tr", {}, [h("td", {}, [d.reason]), h("td", {}, ["-" + d.points])]))),
          ])
        : h("div", { class: "muted" }, ["No deductions -- fully healthy."]),
    ]),
  ]));

  // Base / identity
  app.appendChild(h("div", { class: "section" }, [
    h("h2", {}, ["Identity & Base"]),
    h("div", { class: "card" }, [
      h("table", {}, [
        h("tbody", {}, [
          h("tr", {}, [h("td", {}, ["Identity ID"]), h("td", { class: "mono" }, [(inst.identity && inst.identity.id) || "-"])]),
          h("tr", {}, [h("td", {}, ["Team"]), h("td", {}, [(inst.identity && inst.identity.team) || "-"])]),
          h("tr", {}, [h("td", {}, ["Scope"]), h("td", { class: "mono" }, [(inst.scope || []).join(", ")])]),
          h("tr", {}, [h("td", {}, ["Instance version"]), h("td", { class: "mono" }, [inst.version || "-"])]),
          h("tr", {}, [h("td", {}, ["Built scaffold version"]), h("td", { class: "mono" }, [inst.base.built_scaffold_version || "-"])]),
          h("tr", {}, [h("td", {}, ["Current scaffold version"]), h("td", { class: "mono" }, [inst.base.current_scaffold_version || "-"])]),
          h("tr", {}, [h("td", {}, ["Base status"]), h("td", {}, [h("span", { class: "badge " + (inst.base.status === "stale" ? "warn" : "healthy") }, [inst.base.status])])]),
        ]),
      ]),
    ]),
  ]));

  // CI
  app.appendChild(h("div", { class: "section" }, [
    h("h2", {}, ["CI (mock)"]),
    h("div", { class: "card" }, [
      h("div", {}, [
        h("span", { class: "badge " + (inst.ci.available ? "healthy" : "risk") }, [inst.ci.available ? "available" : "unavailable"]),
        inst.ci.status ? h("span", { class: "muted", style: "margin-left:10px" }, [inst.ci.status]) : null,
      ]),
      inst.ci.steps && inst.ci.steps.length
        ? h("table", { style: "margin-top:10px" }, [
            h("thead", {}, [h("tr", {}, [h("th", {}, ["Step"]), h("th", {}, ["Status"])])]),
            h("tbody", {}, inst.ci.steps.map((s) => h("tr", {}, [h("td", {}, [s.name]), h("td", {}, [s.status])]))),
          ])
        : null,
    ]),
  ]));

  // Managed files (drift table)
  app.appendChild(h("div", { class: "section" }, [
    h("h2", {}, ["Managed Files (drift)"]),
    h("div", { class: "card" }, [
      h("table", {}, [
        h("thead", {}, [h("tr", {}, [h("th", {}, ["Path"]), h("th", {}, ["Status"]), h("th", {}, ["Source"]), h("th", {}, ["Synced at"])])]),
        h("tbody", {}, inst.managed_files.map((f) => h("tr", {}, [
          h("td", { class: "mono" }, [f.path]),
          h("td", {}, [h("span", { class: "badge " + (f.status === "up_to_date" ? "healthy" : f.status === "both_changed" ? "conflict" : "warn") }, [f.status])]),
          h("td", { class: "muted" }, [f.source || "-"]),
          h("td", { class: "muted" }, [f.synced_at || "-"]),
        ]))),
      ]),
    ]),
  ]));

  // Skills
  app.appendChild(h("div", { class: "section" }, [
    h("h2", {}, ["Skills"]),
    h("div", { class: "card" }, [
      inst.skills.length
        ? h("table", {}, [
            h("thead", {}, [h("tr", {}, [h("th", {}, ["Name"]), h("th", {}, ["Tag"]), h("th", {}, ["Version"]), h("th", {}, ["Commit"])])]),
            h("tbody", {}, inst.skills.map((s) => h("tr", {}, [
              h("td", {}, [s.name]),
              h("td", { class: "mono" }, [s.tag || "-"]),
              h("td", { class: "mono" }, [s.version || "-"]),
              h("td", { class: "mono" }, [(s.commit || "").slice(0, 10) || "-"]),
            ]))),
          ])
        : h("div", { class: "muted" }, ["No skills declared."]),
    ]),
  ]));

  // Drafts
  const draftSection = h("div", { class: "section" }, [
    h("h2", {}, ["Change Drafts"]),
  ]);
  const draftCard = h("div", { class: "card" });
  if (draftsResp.drafts.length) {
    draftCard.appendChild(h("table", {}, [
      h("thead", {}, [h("tr", {}, [h("th", {}, ["Draft"]), h("th", {}, ["Op"]), h("th", {}, ["State"]), h("th", {}, ["Updated"])])]),
      h("tbody", {}, draftsResp.drafts.map((d) => h("tr", { class: "clickable", onclick: () => { location.hash = "#/drafts/" + d.draft_id; } }, [
        h("td", { class: "mono" }, [d.draft_id.slice(0, 8)]),
        h("td", {}, [d.operation_type]),
        h("td", {}, [h("span", { class: "badge state" }, [d.state])]),
        h("td", { class: "muted" }, [d.updated_at]),
      ]))),
    ]));
  } else {
    draftCard.appendChild(h("div", { class: "muted" }, ["No drafts yet for this instance."]));
  }
  const newDraftBtn = h("button", {
    class: "primary", style: "margin-top:12px",
    onclick: async () => {
      newDraftBtn.disabled = true;
      try {
        const d = await api("/api/drafts", { method: "POST", body: JSON.stringify({ instance_id: instanceId, operation_type: "CONFIG_EDIT" }) });
        location.hash = "#/drafts/" + d.draft_id;
      } catch (e) {
        alert("Failed to create draft: " + e.message);
      } finally {
        newDraftBtn.disabled = false;
      }
    },
  }, ["+ New CONFIG_EDIT draft"]);
  draftCard.appendChild(newDraftBtn);
  draftSection.appendChild(draftCard);
  app.appendChild(draftSection);
}

// ---- Draft editor -------------------------------------------------------------

const CONFIG_EDIT_ALLOWED_HINT = ".gitignore, instance.yaml, skills.yaml, .env.example, README.md, kb/team/**";

async function renderDraft(draftId) {
  app.innerHTML = "";
  const loading = h("div", { class: "empty-state" }, ["Loading draft..."]);
  app.appendChild(loading);

  let draft;
  try {
    draft = await api("/api/drafts/" + draftId);
  } catch (e) {
    loading.textContent = "Failed to load: " + e.message;
    return;
  }
  loading.remove();

  app.appendChild(h("a", { class: "back-link", href: "#/instances/" + draft.instance_id }, ["← back to " + draft.instance_id]));
  app.appendChild(h("div", { class: "section" }, [
    h("h2", {}, ["Draft " + draft.draft_id.slice(0, 8) + " · " + draft.operation_type]),
    h("div", { class: "muted" }, ["instance: " + draft.instance_id + " · base commit: " + (draft.base_commit || "").slice(0, 10)]),
  ]));

  const states = ["DRAFT", "VALIDATING", "VALIDATED", "BUILD_TESTING", "BUILD_TESTED", "MR_CREATED"];
  const curIdx = states.indexOf(draft.state);
  const flow = h("div", { class: "flow" });
  states.forEach((s, i) => {
    if (i > 0) flow.appendChild(h("span", { class: "arrow" }, ["→"]));
    const cls = i < curIdx ? "done" : (i === curIdx ? "current" : "");
    flow.appendChild(h("span", { class: "step " + cls }, [s]));
  });
  app.appendChild(flow);

  if (draft.mr_url) {
    app.appendChild(h("div", { class: "card", style: "margin-bottom:16px" }, [
      h("div", {}, ["MR created: ", h("span", { class: "mono" }, [draft.mr_url])]),
      h("div", { class: "muted" }, ["branch: " + draft.target_branch]),
    ]));
  }

  const errorBox = h("div", { style: "display:none" });
  app.appendChild(errorBox);

  function showError(e) {
    errorBox.innerHTML = "";
    errorBox.style.display = "block";
    errorBox.appendChild(h("div", { class: "error-box" }, [e.message]));
  }

  // File editor (only while DRAFT)
  if (draft.state === "DRAFT") {
    const filesState = Object.assign({}, draft.files);
    const editorSection = h("div", { class: "section" }, [
      h("h2", {}, ["Files"]),
      h("div", { class: "muted", style: "margin-bottom:8px" }, ["CONFIG_EDIT allowlist: " + CONFIG_EDIT_ALLOWED_HINT]),
    ]);
    const editorCard = h("div", { class: "card" });
    const rows = h("div");
    editorCard.appendChild(rows);

    function addRow(path, content) {
      const pathInput = h("input", { type: "text", value: path || "kb/team/_index.md", placeholder: "path (e.g. kb/team/_index.md)" });
      const textArea = h("textarea", {}, []);
      textArea.value = content || "";
      const row = h("div", { class: "file-editor-row" }, [
        h("div", {}, [pathInput]),
        textArea,
      ]);
      row._pathInput = pathInput;
      row._textArea = textArea;
      rows.appendChild(row);
      return row;
    }

    const fileRows = [];
    const existing = Object.entries(filesState);
    if (existing.length) {
      existing.forEach(([p, c]) => fileRows.push(addRow(p, c)));
    } else {
      fileRows.push(addRow("", ""));
    }

    editorCard.appendChild(h("button", {
      class: "secondary", style: "margin-top:4px",
      onclick: () => { fileRows.push(addRow("", "")); },
    }, ["+ add file"]));

    const saveBtn = h("button", {
      class: "primary", style: "margin-left:8px",
      onclick: async () => {
        const payload = {};
        fileRows.forEach((r) => {
          const p = r._pathInput.value.trim();
          if (p) payload[p] = r._textArea.value;
        });
        try {
          await api("/api/drafts/" + draftId + "/files", { method: "PUT", body: JSON.stringify({ files: payload }) });
          errorBox.style.display = "none";
          renderDraft(draftId);
        } catch (e) {
          showError(e);
        }
      },
    }, ["Save files"]);
    editorCard.appendChild(saveBtn);
    editorSection.appendChild(editorCard);
    app.appendChild(editorSection);
  } else {
    app.appendChild(h("div", { class: "section" }, [
      h("h2", {}, ["Files"]),
      h("div", { class: "card" }, Object.keys(draft.files).length
        ? Object.entries(draft.files).map(([p, c]) => h("div", { style: "margin-bottom:14px" }, [
            h("div", { class: "mono muted" }, [p]),
            h("pre", { class: "mono", style: "white-space:pre-wrap;margin:4px 0" }, [c]),
          ]))
        : [h("div", { class: "muted" }, ["No files in this draft."])]),
    ]));
  }

  // Action buttons
  const toolbar = h("div", { class: "toolbar" });
  function actionButton(label, enabled, onClick) {
    const btn = h("button", {
      class: "primary",
      onclick: async () => {
        btn.disabled = true;
        try {
          await onClick();
          errorBox.style.display = "none";
          renderDraft(draftId);
        } catch (e) {
          showError(e);
        } finally {
          btn.disabled = false;
        }
      },
    }, [label]);
    if (!enabled) btn.disabled = true;
    return btn;
  }

  toolbar.appendChild(actionButton("Validate", draft.state === "DRAFT", () => api("/api/drafts/" + draftId + "/validate", { method: "POST", body: "{}" })));
  toolbar.appendChild(actionButton("Build-test", draft.state === "VALIDATED", () => api("/api/drafts/" + draftId + "/build-test", { method: "POST", body: "{}" })));
  toolbar.appendChild(actionButton("Create MR", draft.state === "BUILD_TESTED", () => api("/api/drafts/" + draftId + "/create-mr", { method: "POST", body: "{}" })));
  app.appendChild(toolbar);
}

// ---- Audit log -----------------------------------------------------------------

async function renderAudit() {
  app.innerHTML = "";
  app.appendChild(h("div", { class: "section" }, [h("h2", {}, ["Audit Log"])]));
  const loading = h("div", { class: "empty-state" }, ["Loading..."]);
  app.appendChild(loading);
  let data;
  try {
    data = await api("/api/audit");
  } catch (e) {
    loading.textContent = "Failed to load: " + e.message;
    return;
  }
  loading.remove();
  const card = h("div", { class: "card" });
  card.appendChild(h("table", {}, [
    h("thead", {}, [h("tr", {}, ["Time", "Instance", "Draft", "Action", "Status", "From", "To", "Actor"].map((t) => h("th", {}, [t])))]),
    h("tbody", {}, data.events.map((e) => h("tr", {}, [
      h("td", { class: "muted" }, [e.created_at]),
      h("td", {}, [e.instance_id || "-"]),
      h("td", { class: "mono" }, [(e.draft_id || "").slice(0, 8)]),
      h("td", {}, [e.action]),
      h("td", {}, [h("span", { class: "badge " + (e.status === "Succeeded" ? "healthy" : e.status === "Failed" ? "risk" : "gray") }, [e.status])]),
      h("td", { class: "muted" }, [e.from_state || "-"]),
      h("td", { class: "muted" }, [e.to_state || "-"]),
      h("td", { class: "muted" }, [e.actor_email || "-"]),
    ]))),
  ]));
  app.appendChild(card);
}

// ---- Router ---------------------------------------------------------------------

function setActiveTab() {
  const hash = location.hash || "#/fleet";
  document.querySelectorAll("nav.tabs button").forEach((btn) => {
    btn.classList.toggle("active", hash.startsWith(btn.dataset.route));
  });
}

async function route() {
  setActiveTab();
  const hash = location.hash || "#/fleet";
  const parts = hash.replace(/^#\//, "").split("/");
  if (parts[0] === "fleet" || parts[0] === "") {
    await renderFleet();
  } else if (parts[0] === "instances" && parts[1]) {
    await renderInstance(decodeURIComponent(parts[1]));
  } else if (parts[0] === "drafts" && parts[1]) {
    await renderDraft(decodeURIComponent(parts[1]));
  } else if (parts[0] === "audit") {
    await renderAudit();
  } else {
    location.hash = "#/fleet";
  }
}

document.querySelectorAll("nav.tabs button").forEach((btn) => {
  btn.addEventListener("click", () => { location.hash = btn.dataset.route; });
});

window.addEventListener("hashchange", route);
// Render exactly once on startup: routing twice concurrently (e.g. an
// immediate call racing DOMContentLoaded) appends two copies of every
// async-fetched view.
if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", route);
} else {
  route();
}
