(() => {
  "use strict";

  const data = JSON.parse(document.getElementById("audit-data").textContent);
  const storageKey = `penta-visual-audit:${data.candidate.sha256}`;
  const uiStorageKey = `${storageKey}:queue-ui-v1`;
  const stateSchema = "penta-visual-human-review-state-v1";
  const exportSchema = "penta-visual-human-review-v1";
  const verdicts = new Set(["unreviewed", "good", "issue", "recapture", "intentional"]);
  const categories = data.categories;
  const flatItems = categories.flatMap(category => category.items.map(item => ({item, category})));
  const allIds = flatItems.map(row => row.item.audit_id);
  const auditIds = new Set(allIds);
  const rowById = new Map(flatItems.map(row => [row.item.audit_id, row]));
  const queryParameters = new URLSearchParams(window.location.search);
  const requestedPreset = queryParameters.get("preset") || "";
  const activePreset = data.review_presets?.[requestedPreset] || null;
  const presetRows = activePreset ? asArray(activePreset.items) : [];
  const presetRowById = new Map(presetRows.map(row => [row.audit_id, row]));
  const reviewIds = activePreset
    ? presetRows.map(row => row.audit_id).filter(id => auditIds.has(id))
    : allIds;
  const reviewIdSet = new Set(reviewIds);
  const evidenceFor = id => rowById.get(id)?.item.evidence_sha256 || "";
  function asArray(value) { return Array.isArray(value) ? value : []; }

  const esc = value => String(value ?? "").replace(/[&<>\"']/g, char => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  })[char]);

  function objectFromStorage(key) {
    try {
      const value = JSON.parse(localStorage.getItem(key) || "{}");
      return value && typeof value === "object" && !Array.isArray(value) ? value : {};
    } catch (_error) {
      return {};
    }
  }

  let saved = objectFromStorage(storageKey);
  let ui = {
    queueMode: true,
    cursor: null,
    query: "",
    category: "all",
    machine: "all",
    human: "unreviewed",
    side: "both",
    ...objectFromStorage(uiStorageKey),
  };
  if (!reviewIdSet.has(ui.cursor)) ui.cursor = null;
  let activeId = ui.cursor;
  let serverOnline = false;
  let serverRevision = 0;
  let saveTimer = null;
  let saveInFlight = false;
  let saveAgain = false;

  function saveLocal() {
    try {
      localStorage.setItem(storageKey, JSON.stringify(saved));
      localStorage.setItem(uiStorageKey, JSON.stringify(ui));
    } catch (_error) {
      setSaveState("Browser storage failed; disk save is still attempted.", "failed");
    }
  }

  function reviewTime(row) {
    const value = Date.parse(row?.updated_at || "");
    return Number.isFinite(value) ? value : 0;
  }

  function mergeReviews(incoming) {
    if (!incoming || typeof incoming !== "object" || Array.isArray(incoming)) return false;
    let changed = false;
    Object.entries(incoming).forEach(([id, row]) => {
      if (!auditIds.has(id) || !row || typeof row !== "object") return;
      const verdict = verdicts.has(row.verdict) ? row.verdict : "unreviewed";
      const normalized = {
        verdict,
        notes: String(row.notes || ""),
        updated_at: String(row.updated_at || ""),
        evidence_sha256: evidenceFor(id),
      };
      const suppliedEvidence = String(row.evidence_sha256 || "");
      const stale = verdict !== "unreviewed" && suppliedEvidence !== evidenceFor(id);
      if (stale) {
        normalized.verdict = "unreviewed";
        normalized.needs_revalidation = true;
        normalized.previous_verdict = verdict;
        normalized.previous_evidence_sha256 = suppliedEvidence || "legacy-unbound";
      } else if (row.needs_revalidation && verdict === "unreviewed") {
        normalized.needs_revalidation = true;
        normalized.previous_verdict = String(row.previous_verdict || "unreviewed");
        normalized.previous_evidence_sha256 = String(row.previous_evidence_sha256 || "");
      }
      if (!saved[id] || reviewTime(normalized) >= reviewTime(saved[id])) {
        if (JSON.stringify(saved[id]) !== JSON.stringify(normalized)) changed = true;
        saved[id] = normalized;
      }
    });
    return changed;
  }

  function statePayload() {
    return {
      schema: stateSchema,
      candidate_sha256: data.candidate.sha256,
      audit_evidence_sha256: data.audit_evidence_sha256,
      updated_at: new Date().toISOString(),
      revision: serverRevision,
      cursor: activeId,
      reviews: saved,
    };
  }

  function setSaveState(message, kind = "") {
    const node = document.getElementById("save-state");
    if (!node) return;
    node.textContent = message;
    node.classList.remove("saved", "saving", "failed");
    if (kind) node.classList.add(kind);
  }

  async function saveToServer() {
    if (saveInFlight) {
      saveAgain = true;
      return;
    }
    clearTimeout(saveTimer);
    saveTimer = null;
    saveInFlight = true;
    setSaveState("Saving browser + disk checkpoints…", "saving");
    try {
      const response = await fetch("/api/review", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(statePayload()),
      });
      if (!response.ok) throw new Error(`review server returned ${response.status}`);
      const state = await response.json();
      if (state.candidate_sha256 !== data.candidate.sha256) throw new Error("review server candidate mismatch");
      mergeReviews(state.reviews);
      serverRevision = Number(state.revision || 0);
      serverOnline = true;
      saveLocal();
      const time = new Date(state.updated_at || Date.now()).toLocaleTimeString();
      setSaveState(`Saved to disk + browser · ${time}`, "saved");
    } catch (error) {
      serverOnline = false;
      setSaveState(`Browser saved; disk checkpoint failed: ${error.message}`, "failed");
    } finally {
      saveInFlight = false;
      if (saveAgain) {
        saveAgain = false;
        saveToServer();
      }
    }
  }

  function scheduleSave() {
    saveLocal();
    setSaveState(serverOnline ? "Browser saved · disk save queued…" : "Browser saved · reconnecting disk checkpoint…", "saving");
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveToServer, 350);
  }

  async function loadServerState() {
    try {
      const response = await fetch("/api/review", {cache: "no-store"});
      if (!response.ok) throw new Error(`review server returned ${response.status}`);
      const state = await response.json();
      if (state.schema !== stateSchema) throw new Error("unsupported disk-checkpoint schema");
      if (state.candidate_sha256 !== data.candidate.sha256) throw new Error("disk checkpoint belongs to another candidate");
      const localBefore = JSON.stringify(saved);
      mergeReviews(state.reviews);
      if (reviewIdSet.has(state.cursor)) ui.cursor = state.cursor;
      serverRevision = Number(state.revision || 0);
      serverOnline = true;
      saveLocal();
      setSaveState(`Disk checkpoint loaded · ${Object.keys(state.reviews || {}).length} saved items`, "saved");
      // Re-submit the merged view once. This copies any newer browser-only
      // rows to disk without allowing an older server row to erase them.
      if (Object.keys(saved).length || JSON.stringify(saved) !== localBefore) scheduleSave();
    } catch (error) {
      serverOnline = false;
      setSaveState(`Browser backup only: ${error.message}`, "failed");
    }
  }

  function summary() {
    const human = reviewIds.map(id => saved[id]).filter(Boolean);
    const reviewed = human.filter(row => row.verdict && row.verdict !== "unreviewed").length;
    const issues = human.filter(row => row.verdict === "issue" || row.verdict === "recapture").length;
    const coverageClass = data.coverage.missing_items ? "warn" : "good";
    document.getElementById("summary").innerHTML = `
      <div class="metric ${coverageClass}"><strong>${data.coverage.covered_items}/${data.coverage.expected_items}</strong><span>machine-covered audit items</span></div>
      <div class="metric ${data.coverage.failed_categories ? "bad" : "good"}"><strong>${data.coverage.failed_categories}</strong><span>categories with machine gaps</span></div>
      <div class="metric"><strong>${data.media.unique_images}</strong><span>content-hashed images</span></div>
      ${activePreset ? `<div class="metric good"><strong>${reviewIds.length}</strong><span>fixed-defect samples only</span></div>` : ""}
      <div class="metric ${issues ? "bad" : "good"}"><strong>${reviewed}/${reviewIds.length}</strong><span>human-reviewed · ${issues} flagged</span></div>`;
  }

  function palettes(rows) {
    rows = asArray(rows);
    if (!rows.length) return "";
    return `<div class="palette-strip">${rows.map(row => `
      <div class="palette-row" title="${esc(row.source)} · ${esc(asArray(row.bgr555).join(" "))}">
        <code>${esc(row.short_name || row.source)}</code>
        ${asArray(row.rgb).map(color => `<span class="swatch" style="background:${esc(color)}"></span>`).join("")}
      </div>`).join("")}</div>`;
  }

  function imageFigure(image) {
    return `<figure class="shot" data-side="${esc(image.side || "dx")}">
      <img loading="lazy" src="${esc(image.media)}" alt="${esc(image.alt || image.caption)}" data-caption="${esc(image.caption)}">
      <figcaption>${esc(image.caption)}</figcaption>
    </figure>`;
  }

  function evenlySpaced(rows, limit) {
    if (limit <= 1) return rows.slice(0, 1);
    if (rows.length <= limit) return rows;
    const indexes = new Set();
    for (let index = 0; index < limit; index++) {
      indexes.add(Math.round(index * (rows.length - 1) / (limit - 1)));
    }
    return [...indexes].sort((left, right) => left - right).map(index => rows[index]);
  }

  function compactImages(images, item) {
    images = asArray(images);
    if (!activePreset) return images;
    const preset = presetRowById.get(item.audit_id) || {};
    const pairs = new Map();
    images.forEach(image => {
      if (!image.pair_key) return;
      const pair = pairs.get(image.pair_key) || [];
      pair.push(image);
      pairs.set(image.pair_key, pair);
    });
    if (pairs.size) {
      const selected = evenlySpaced([...pairs.keys()], Number(preset.max_pairs || 3));
      const selectedSet = new Set(selected);
      return images.filter(image => selectedSet.has(image.pair_key));
    }
    return evenlySpaced(images, Number(preset.max_images || 4));
  }

  function imageGrid(images) {
    images = asArray(images);
    const pairs = new Map();
    images.forEach(image => {
      if (!image.pair_key) return;
      const pair = pairs.get(image.pair_key) || {};
      pair[image.side] = image;
      pairs.set(image.pair_key, pair);
    });
    if (pairs.size && [...pairs.values()].every(pair => pair.og && pair.dx)) {
      return `<div class="image-grid paired">${[...pairs.entries()].map(([key, pair]) => `
        <figure class="pair">
          <div class="pair-images">
            <div data-side="og"><span class="side-label og">OG</span><img loading="lazy" src="${esc(pair.og.media)}" alt="${esc(pair.og.alt)}" data-caption="${esc(pair.og.caption)}"></div>
            <div data-side="dx"><span class="side-label dx">DX</span><img loading="lazy" src="${esc(pair.dx.media)}" alt="${esc(pair.dx.alt)}" data-caption="${esc(pair.dx.caption)}"></div>
          </div>
          <figcaption>${esc(key)}</figcaption>
        </figure>`).join("")}</div>`;
    }
    return `<div class="image-grid">${images.map(imageFigure).join("")}</div>`;
  }

  function card(item, category) {
    const review = saved[item.audit_id] || {verdict: "unreviewed", notes: ""};
    const notes = asArray(item.machine_notes);
    const fullImages = asArray(item.images);
    const images = compactImages(fullImages, item);
    const preset = presetRowById.get(item.audit_id);
    const sampledPairs = new Set(images.map(image => image.pair_key).filter(Boolean)).size;
    const fullPairs = new Set(fullImages.map(image => image.pair_key).filter(Boolean)).size;
    const subtitle = activePreset && images.length < fullImages.length
      ? (sampledPairs
        ? `${sampledPairs} sampled OG/DX pairs · ${fullPairs} pairs in full receipt`
        : `${images.length} sampled images · ${fullImages.length} in full receipt`)
      : (item.subtitle || `${images.length} image${images.length === 1 ? "" : "s"}`);
    const reviewClass = review.verdict === "good" ? "human-good" :
      review.verdict === "issue" ? "human-issue" :
      review.verdict === "recapture" ? "human-recapture" : "";
    return `<article class="card ${reviewClass}" id="${esc(item.audit_id)}" tabindex="-1" data-category="${esc(category.id)}" data-machine="${esc(item.status)}" data-search="${esc(`${item.label} ${item.subtitle || ""} ${notes.join(" ")}`.toLowerCase())}">
      <div class="card-head"><div><h3>${esc(item.label)}</h3><div class="subtitle">${esc(subtitle)}</div></div><span class="badge ${esc(item.status)}">${esc(item.status)}</span></div>
      ${preset ? `<div class="sample-class"><strong>${esc(preset.label)}</strong><span>${esc(preset.reason)}</span></div>` : ""}
      ${palettes(item.palettes)}
      ${images.length ? imageGrid(images) : `<div class="empty">No hash-bound capture. This is a real coverage gap.</div>`}
      ${notes.length ? `<ul class="machine-notes">${notes.map(note => `<li class="${item.status === "covered" ? "" : "problem"}">${esc(note)}</li>`).join("")}</ul>` : ""}
      ${review.needs_revalidation ? `<div class="revalidation">Evidence changed since the prior <strong>${esc(review.previous_verdict)}</strong> verdict. Your note is preserved; review these new frames again.</div>` : ""}
      <div class="review">
        <div><label>Verdict</label><select data-review="verdict" data-id="${esc(item.audit_id)}">
          ${[["unreviewed","U · Unreviewed"],["good","G · Looks good"],["issue","I · Visual issue"],["recapture","R · Needs recapture"],["intentional","A · Intentional / accepted"]].map(([value,label]) => `<option value="${value}" ${review.verdict === value ? "selected" : ""}>${label}</option>`).join("")}
        </select></div>
        <div><label>Human notes</label><textarea data-review="notes" data-id="${esc(item.audit_id)}" placeholder="Press N, then describe color bleed, gray edge, wrong material, flicker…">${esc(review.notes || "")}</textarea></div>
        <div class="review-actions"><span>Issue opens notes. Other completed verdicts save and advance.</span><button type="button" data-review-next data-id="${esc(item.audit_id)}">Save &amp; next →</button></div>
      </div>
    </article>`;
  }

  function reviewedCount(category) {
    return category.items.filter(item => reviewIdSet.has(item.audit_id) && (saved[item.audit_id]?.verdict || "unreviewed") !== "unreviewed").length;
  }

  function render() {
    const displayedCategories = categories.map(category => ({
      ...category,
      items: activePreset ? category.items.filter(item => reviewIdSet.has(item.audit_id)) : category.items,
    })).filter(category => category.items.length);
    const displayedCategoryIds = new Set(displayedCategories.map(category => category.id));
    const presetBanner = document.getElementById("preset-banner");
    presetBanner.innerHTML = activePreset ? `<strong>${esc(activePreset.title)}</strong><span>${esc(activePreset.description)}</span><a href="./">Open the full 260-item audit</a>` : "";
    presetBanner.classList.toggle("hidden", !activePreset);
    document.getElementById("rail").innerHTML = `<h2>Human review</h2>` + displayedCategories.map(category => `
      <a href="#category-${esc(category.id)}" data-rail-category="${esc(category.id)}"><span>${esc(category.title)}</span><small>${reviewedCount(category)}/${activePreset ? category.items.length : category.expected_items}</small></a>`).join("");
    document.getElementById("category-filter").innerHTML = `<option value="all">All categories</option>` + displayedCategories.map(category => `<option value="${esc(category.id)}">${esc(category.title)}</option>`).join("");
    document.getElementById("content").innerHTML = displayedCategories.map(category => `
      <section class="category" id="category-${esc(category.id)}" data-category-section="${esc(category.id)}">
        <div class="category-head"><div><div class="eyebrow">${esc(category.human_priority)} priority</div><h2>${esc(category.title)}</h2><div class="category-copy">${reviewedCount(category)}/${activePreset ? category.items.length : category.expected_items} reviewed · ${esc(category.description)}</div></div><span class="badge ${category.missing_items ? "partial" : "covered"}">${category.covered_items}/${category.expected_items}</span></div>
        <div class="cards">${category.items.map(item => card(item, category)).join("")}</div>
      </section>`).join("");
    document.getElementById("search").value = ui.query || "";
    document.getElementById("category-filter").value = displayedCategoryIds.has(ui.category) ? ui.category : "all";
    document.getElementById("machine-filter").value = ui.machine || "all";
    document.getElementById("human-filter").value = ui.human || "unreviewed";
    document.getElementById("side-filter").value = ui.side || "both";
    document.body.classList.toggle("queue-mode", ui.queueMode !== false);
    summary();
    bindCards();
    applySideFilter();
  }

  function reviewFor(id) {
    return saved[id] || {verdict: "unreviewed", notes: ""};
  }

  function refreshCard(id) {
    const cardNode = document.getElementById(id);
    if (!cardNode) return;
    const verdict = reviewFor(id).verdict;
    cardNode.classList.remove("human-good", "human-issue", "human-recapture");
    if (verdict === "good") cardNode.classList.add("human-good");
    if (verdict === "issue") cardNode.classList.add("human-issue");
    if (verdict === "recapture") cardNode.classList.add("human-recapture");
  }

  function persist(id, field, value) {
    saved[id] = saved[id] || {verdict: "unreviewed", notes: ""};
    saved[id][field] = value;
    saved[id].evidence_sha256 = evidenceFor(id);
    if (field === "verdict" && value !== "unreviewed") {
      delete saved[id].needs_revalidation;
      delete saved[id].previous_verdict;
      delete saved[id].previous_evidence_sha256;
    }
    saved[id].updated_at = new Date().toISOString();
    refreshCard(id);
    summary();
    scheduleSave();
    if (!ui.queueMode) applyFilters();
    updateQueuePosition();
  }

  function cardMatches(cardNode) {
    if (!cardNode) return false;
    const query = document.getElementById("search").value.trim().toLowerCase();
    const category = document.getElementById("category-filter").value;
    const machine = document.getElementById("machine-filter").value;
    const human = document.getElementById("human-filter").value;
    const review = reviewFor(cardNode.id);
    return (!query || cardNode.dataset.search.includes(query)) &&
      (category === "all" || cardNode.dataset.category === category) &&
      (machine === "all" || (machine === "gaps" ? cardNode.dataset.machine !== "covered" : cardNode.dataset.machine === machine)) &&
      (human === "all" || review.verdict === human);
  }

  function matchingIds() {
    return reviewIds.filter(id => {
      const cardNode = document.getElementById(id);
      return cardNode && cardMatches(cardNode);
    });
  }

  function applyFilters() {
    document.querySelectorAll(".card").forEach(cardNode => {
      const visible = cardMatches(cardNode) || (ui.queueMode && cardNode.id === activeId);
      cardNode.classList.toggle("hidden", !visible);
    });
    document.querySelectorAll("[data-category-section]").forEach(section => {
      const isActiveCategory = section.dataset.categorySection === rowById.get(activeId)?.category.id;
      section.classList.toggle("queue-category", ui.queueMode && isActiveCategory);
      section.classList.toggle("hidden", !ui.queueMode && !section.querySelector(".card:not(.hidden)"));
    });
    updateQueuePosition();
  }

  function firstUnreviewedAfter(id) {
    const start = Math.max(-1, reviewIds.indexOf(id));
    for (let offset = 1; offset <= reviewIds.length; offset++) {
      const candidate = reviewIds[(start + offset) % reviewIds.length];
      if (reviewFor(candidate).verdict === "unreviewed") return candidate;
    }
    return null;
  }

  function nextMatching(fromId, delta) {
    const start = Math.max(0, reviewIds.indexOf(fromId));
    for (let offset = 1; offset <= reviewIds.length; offset++) {
      const index = (start + delta * offset + reviewIds.length * 2) % reviewIds.length;
      const candidate = reviewIds[index];
      const cardNode = document.getElementById(candidate);
      if (cardNode && cardMatches(cardNode)) return candidate;
    }
    return fromId || reviewIds[0];
  }

  function activate(id, {scroll = true, checkpoint = true} = {}) {
    if (!reviewIdSet.has(id)) return;
    document.querySelectorAll(".queue-active").forEach(node => node.classList.remove("queue-active"));
    document.querySelectorAll(".queue-category").forEach(node => node.classList.remove("queue-category"));
    activeId = id;
    ui.cursor = id;
    const cardNode = document.getElementById(id);
    const section = cardNode?.closest("[data-category-section]");
    cardNode?.classList.add("queue-active");
    section?.classList.add("queue-category");
    if (checkpoint) {
      saveLocal();
      scheduleSave();
    }
    applyFilters();
    if (scroll && cardNode) {
      cardNode.scrollIntoView({behavior: "smooth", block: "start"});
      cardNode.focus({preventScroll: true});
    }
  }

  function move(delta) {
    activate(nextMatching(activeId, delta));
  }

  function resumeUnreviewed() {
    ui.human = "unreviewed";
    document.getElementById("human-filter").value = "unreviewed";
    const target = reviewFor(activeId).verdict === "unreviewed" ? activeId : firstUnreviewedAfter(activeId);
    if (target) activate(target);
    else setSaveState(`All ${reviewIds.length} displayed items have a verdict.`, "saved");
  }

  function updateQueuePosition() {
    const node = document.getElementById("queue-position");
    if (!node || !activeId) return;
    const global = reviewIds.indexOf(activeId) + 1;
    const queue = matchingIds();
    const queueIndex = queue.indexOf(activeId);
    const row = rowById.get(activeId);
    const scope = queueIndex >= 0 ? `${queueIndex + 1}/${queue.length} in current queue` : `${queue.length} match current filters`;
    node.textContent = `${activePreset ? "Sample" : "Item"} ${global}/${reviewIds.length} · ${scope} · ${row?.category.title || ""}`;
    const toggle = document.getElementById("queue-toggle");
    toggle.textContent = ui.queueMode ? "Show all cards" : "Use review queue";
    toggle.setAttribute("aria-pressed", String(ui.queueMode));
  }

  function toggleQueue() {
    ui.queueMode = !ui.queueMode;
    document.body.classList.toggle("queue-mode", ui.queueMode);
    saveLocal();
    applyFilters();
    if (ui.queueMode && activeId) activate(activeId);
  }

  function applySideFilter() {
    const value = document.getElementById("side-filter").value;
    document.body.dataset.side = value;
    document.querySelectorAll("[data-side]").forEach(node => {
      node.classList.toggle("hidden", value !== "both" && node.dataset.side !== value);
    });
  }

  function focusNotes(id = activeId) {
    const notes = document.querySelector(`textarea[data-id="${CSS.escape(id)}"]`);
    if (notes) {
      notes.focus();
      notes.setSelectionRange(notes.value.length, notes.value.length);
    }
  }

  function advanceFrom(id) {
    if (!reviewIdSet.has(id)) return;
    if (activeId !== id) activate(id, {scroll: false});
    saveToServer();
    move(1);
  }

  function mouseVerdict(id, verdict) {
    persist(id, "verdict", verdict);
    if (!ui.queueMode) return;
    if (activeId !== id) activate(id, {scroll: false});
    if (verdict === "issue") focusNotes(id);
    else if (verdict !== "unreviewed") move(1);
  }

  function mark(verdict, action) {
    if (!activeId) return;
    const select = document.querySelector(`select[data-id="${CSS.escape(activeId)}"]`);
    if (select) select.value = verdict;
    persist(activeId, "verdict", verdict);
    if (action === "next") move(1);
    if (action === "notes") focusNotes();
  }

  function bindCards() {
    document.querySelectorAll("select[data-review='verdict']").forEach(control => {
      control.addEventListener("change", () => mouseVerdict(control.dataset.id, control.value));
    });
    document.querySelectorAll("textarea[data-review='notes']").forEach(control => {
      control.addEventListener("input", () => persist(control.dataset.id, "notes", control.value));
      control.addEventListener("keydown", event => {
        if (event.key === "Enter" && event.ctrlKey) {
          event.preventDefault();
          persist(control.dataset.id, "notes", control.value);
          advanceFrom(control.dataset.id);
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          control.blur();
          document.getElementById(control.dataset.id)?.focus();
        }
      });
    });
    document.querySelectorAll("[data-review-next]").forEach(control => {
      control.addEventListener("click", () => advanceFrom(control.dataset.id));
    });
    document.querySelectorAll(".shot img, .pair img").forEach(image => image.addEventListener("click", () => {
      const dialog = document.getElementById("lightbox");
      dialog.querySelector("img").src = image.src;
      dialog.querySelector("p").textContent = image.dataset.caption || image.alt;
      dialog.showModal();
    }));
    document.querySelectorAll("[data-rail-category]").forEach(link => link.addEventListener("click", event => {
      if (!ui.queueMode) return;
      event.preventDefault();
      ui.category = link.dataset.railCategory;
      document.getElementById("category-filter").value = ui.category;
      const target = matchingIds()[0];
      if (target) activate(target);
    }));
  }

  function bindShell() {
    ["search", "category-filter", "machine-filter", "human-filter"].forEach(id => {
      const control = document.getElementById(id);
      control.addEventListener(id === "search" ? "input" : "change", () => {
        ui.query = document.getElementById("search").value;
        ui.category = document.getElementById("category-filter").value;
        ui.machine = document.getElementById("machine-filter").value;
        ui.human = document.getElementById("human-filter").value;
        saveLocal();
        applyFilters();
        if (ui.queueMode && !cardMatches(document.getElementById(activeId))) {
          const target = matchingIds()[0];
          if (target) activate(target);
        }
      });
    });
    document.getElementById("side-filter").addEventListener("change", event => {
      ui.side = event.target.value;
      saveLocal();
      applySideFilter();
    });
    document.getElementById("queue-toggle").addEventListener("click", toggleQueue);
    document.getElementById("queue-previous").addEventListener("click", () => move(-1));
    document.getElementById("queue-next").addEventListener("click", () => move(1));
    document.getElementById("queue-resume").addEventListener("click", resumeUnreviewed);
    document.getElementById("save-now").addEventListener("click", saveToServer);
    document.getElementById("shortcut-help").addEventListener("click", () => document.getElementById("shortcut-dialog").showModal());
    document.getElementById("export-review").addEventListener("click", exportReview);
    document.getElementById("import-review").addEventListener("change", importReview);
    document.getElementById("lightbox").addEventListener("click", event => {
      if (event.target.tagName !== "IMG") event.currentTarget.close();
    });
    document.addEventListener("keydown", keyboardReview);
    window.addEventListener("pagehide", () => {
      saveLocal();
      const body = new Blob([JSON.stringify(statePayload())], {type: "application/json"});
      navigator.sendBeacon?.("/api/review", body);
    });
  }

  function exportReview() {
    const payload = {schema: exportSchema, candidate_sha256: data.candidate.sha256, exported_at: new Date().toISOString(), reviews: saved};
    const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], {type: "application/json"});
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `penta-visual-review-${data.candidate.sha256.slice(0, 12)}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function importReview(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const incoming = JSON.parse(reader.result);
        if (incoming.schema !== exportSchema) throw new Error("Unsupported review format.");
        if (incoming.candidate_sha256 !== data.candidate.sha256) throw new Error("Review belongs to a different ROM hash.");
        if (!incoming.reviews || typeof incoming.reviews !== "object" || Array.isArray(incoming.reviews)) throw new Error("Review file has no review map.");
        mergeReviews(incoming.reviews);
        render();
        activate(activeId || firstUnreviewedAfter(null), {scroll: false});
        saveToServer();
      } catch (error) {
        alert(error.message || "Could not import review file.");
      } finally {
        event.target.value = "";
      }
    };
    reader.readAsText(file);
  }

  function keyboardReview(event) {
    const target = event.target;
    const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || target.isContentEditable;
    if (typing || document.getElementById("lightbox").open || document.getElementById("shortcut-dialog").open) return;
    const key = event.key.toLowerCase();
    const action = {
      g: () => mark("good", "next"), "1": () => mark("good", "next"),
      i: () => mark("issue", "notes"), "2": () => mark("issue", "notes"),
      r: () => mark("recapture", "next"), "3": () => mark("recapture", "next"),
      a: () => mark("intentional", "next"), "4": () => mark("intentional", "next"),
      u: () => mark("unreviewed"), "0": () => mark("unreviewed"),
      j: () => move(1), arrowright: () => move(1),
      k: () => move(-1), arrowleft: () => move(-1),
      n: focusNotes,
      "?": () => document.getElementById("shortcut-dialog").showModal(),
    }[key];
    if (action) {
      event.preventDefault();
      action();
    }
  }

  async function bootstrap() {
    // Render the browser-backed queue before waiting on localhost. A slow or
    // restarted review server must never leave the whole audit blank.
    render();
    bindShell();
    let target = ui.cursor;
    if (!target || reviewFor(target).verdict !== "unreviewed") {
      target = firstUnreviewedAfter(target);
    }
    if (!target) target = reviewIds[0];
    activate(target, {scroll: false, checkpoint: false});

    await loadServerState();
    render();
    target = ui.cursor;
    if (!target || reviewFor(target).verdict !== "unreviewed") {
      target = firstUnreviewedAfter(target);
    }
    if (!target) target = reviewIds[0];
    activate(target, {scroll: false});
  }

  bootstrap();
})();
