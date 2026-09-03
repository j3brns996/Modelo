"use strict";

document.addEventListener("alpine:init", () => {
  window.Alpine.data("catalogueExplorer", () => ({
    query: "",
    filters: {},
    sort: "name-asc",
    view: "grid",
    comparison: [],
    rows: [],
    cards: [],
    filterButtons: [],
    searchMax: 200,
    compareMax: 4,
    viewStorageKey: "",
    defaultView: "grid",

    init() {
      this.rows = [...this.$root.querySelectorAll("[data-catalogue-row]")].map((element, index) => ({ element, index }));
      this.cards = [...this.$root.querySelectorAll("[data-catalogue-card]")].map((element, index) => ({ element, index }));
      this.filterButtons = [...this.$root.querySelectorAll("[data-filter][data-value]")];
      this.searchMax = Number(this.$root.dataset.searchMax);
      this.compareMax = Number(this.$root.dataset.compareMax);
      this.viewStorageKey = this.$root.dataset.viewStorageKey;
      this.defaultView = this.$root.dataset.defaultView === "table" ? "table" : "grid";
      this.readUrl();
      const form = this.$root.querySelector("[data-catalogue-filters]");
      form.addEventListener("submit", event => event.preventDefault());
      const dialog = this.$root.querySelector("[data-comparison-dialog]");
      dialog.addEventListener("cancel", () => this.closeComparison());
      for (const button of this.$root.querySelectorAll("[data-compare-toggle]")) button.hidden = false;
      this.apply(false);
      this.updateComparison();
    },

    readUrl() {
      const parameters = new URL(window.location.href).searchParams;
      this.query = (parameters.get("q") || "").slice(0, this.searchMax);
      this.$root.querySelector("[data-search]").value = this.query;
      for (const button of this.filterButtons) {
        const key = button.dataset.filter;
        const allowed = new Set(this.filterButtons.filter(item => item.dataset.filter === key).map(item => item.dataset.value));
        this.filters[key] = parameters.getAll(key).filter(value => allowed.has(value));
      }
      const allowedSorts = new Set(["name-asc", "name-desc", "models-first", "offerings-first"]);
      const requestedSort = parameters.get("sort");
      this.sort = allowedSorts.has(requestedSort) ? requestedSort : "name-asc";
      this.$root.querySelector("[data-sort]").value = this.sort;
      this.view = this.readViewPreference(parameters);
      const modelKeys = new Set(this.cards.map(card => card.element.dataset.key));
      this.comparison = [...new Set(parameters.getAll("compare"))].filter(key => modelKeys.has(key)).slice(0, this.compareMax);
    },

    writeUrl() {
      const url = new URL(window.location.href);
      const owned = ["q", "sort", "view", "compare", ...new Set(this.filterButtons.map(button => button.dataset.filter))];
      for (const key of owned) url.searchParams.delete(key);
      if (this.query) url.searchParams.set("q", this.query);
      for (const key of Object.keys(this.filters).sort()) {
        for (const value of [...this.filters[key]].sort()) url.searchParams.append(key, value);
      }
      if (this.sort !== "name-asc") url.searchParams.set("sort", this.sort);
      if (this.view !== this.defaultView) url.searchParams.set("view", this.view);
      for (const key of this.comparison) url.searchParams.append("compare", key);
      window.history.replaceState(null, "", url);
    },

    readViewPreference(parameters) {
      const requested = parameters.get("view");
      if (requested === "grid" || requested === "table") return requested;
      try {
        const stored = window.localStorage.getItem(this.viewStorageKey);
        return stored === "grid" || stored === "table" ? stored : this.defaultView;
      } catch (_error) {
        return this.defaultView;
      }
    },

    writeViewPreference() {
      try {
        window.localStorage.setItem(this.viewStorageKey, this.view);
      } catch (_error) {
        // Storage can be unavailable in hardened browsers; URL state still works.
      }
    },

    searchChanged(event) {
      this.query = event.target.value.toLocaleLowerCase("en-GB").trim().slice(0, this.searchMax);
      this.apply();
    },

    toggleFilter(event) {
      const button = event.currentTarget;
      const key = button.dataset.filter;
      const value = button.dataset.value;
      const selected = new Set(this.filters[key] || []);
      selected.has(value) ? selected.delete(value) : selected.add(value);
      this.filters[key] = [...selected];
      if (key === "kind" && value === "offering" && selected.has(value) && this.view === "grid") {
        this.view = "table";
        this.writeViewPreference();
      }
      this.apply();
    },

    toggleAdvanced() {
      const button = this.$root.querySelector("[data-advanced-toggle]");
      const panel = this.$root.querySelector("[data-advanced-filters]");
      const expanded = button.getAttribute("aria-expanded") === "true";
      button.setAttribute("aria-expanded", String(!expanded));
      panel.hidden = expanded;
    },

    sortChanged(event) {
      this.sort = event.currentTarget.value;
      this.apply();
    },

    changeView(event) {
      this.view = event.currentTarget.dataset.view === "grid" ? "grid" : "table";
      this.writeViewPreference();
      this.apply();
    },

    clearAll() {
      this.query = "";
      this.$root.querySelector("[data-search]").value = "";
      for (const key of Object.keys(this.filters)) this.filters[key] = [];
      this.apply();
      this.$root.querySelector("[data-search]").focus();
    },

    matches(row) {
      const needle = this.query.toLocaleLowerCase("en-GB");
      const textMatches = !needle || row.element.dataset.searchText.toLocaleLowerCase("en-GB").includes(needle);
      const facetsMatch = Object.entries(this.filters).every(([key, selected]) => {
        if (!selected.length) return true;
        const values = (row.element.getAttribute("data-" + key) || "").split("|").filter(Boolean);
        return selected.some(value => values.includes(value));
      });
      return textMatches && facetsMatch;
    },

    compareRows(left, right) {
      const nameOrder = left.element.dataset.name.localeCompare(right.element.dataset.name, "en-GB", { sensitivity: "base", numeric: true });
      if (this.sort === "name-desc") return nameOrder ? -nameOrder : left.index - right.index;
      if (this.sort === "models-first" || this.sort === "offerings-first") {
        const preferred = this.sort === "models-first" ? "model" : "offering";
        const kindOrder = Number(right.element.dataset.kind === preferred) - Number(left.element.dataset.kind === preferred);
        return kindOrder || nameOrder || left.index - right.index;
      }
      return nameOrder || left.index - right.index;
    },

    apply(write = true) {
      const body = this.$root.querySelector("[data-catalogue-body]");
      const grid = this.$root.querySelector("[data-catalogue-grid]");
      const items = this.view === "grid" ? this.cards : this.rows;
      const ordered = [...items].sort((left, right) => this.compareRows(left, right));
      let visible = 0;
      for (const item of this.rows) item.element.hidden = this.view === "table" ? !this.matches(item) : false;
      for (const item of this.cards) item.element.hidden = this.view === "grid" ? !this.matches(item) : false;
      for (const row of ordered) {
        if (!row.element.hidden) visible += 1;
        (this.view === "grid" ? grid : body).append(row.element);
      }
      const total = items.length;
      const noun = this.view === "grid" ? (total === 1 ? "model" : "models") : (total === 1 ? "record" : "records");
      this.$root.querySelector("[data-result-count]").textContent = `Showing ${visible} of ${total} ${noun}`;
      this.$root.querySelector("[data-no-results]").hidden = visible !== 0;
      this.$root.dataset.view = this.view;
      for (const button of this.$root.querySelectorAll("[data-view]")) button.setAttribute("aria-pressed", String(button.dataset.view === this.view));
      for (const button of this.filterButtons) button.setAttribute("aria-pressed", String((this.filters[button.dataset.filter] || []).includes(button.dataset.value)));
      this.renderActiveFilters();
      if (write) this.writeUrl();
    },

    renderActiveFilters() {
      const container = this.$root.querySelector("[data-active-filters]");
      const active = this.filterButtons.filter(button => (this.filters[button.dataset.filter] || []).includes(button.dataset.value));
      container.replaceChildren();
      if (this.query) container.append(this.removeButton("Search", this.query, "query", ""));
      for (const button of active) container.append(this.removeButton(button.dataset.filterLabel, button.textContent, button.dataset.filter, button.dataset.value));
      container.hidden = !container.childElementCount;
      this.$root.querySelector("[data-clear-all]").hidden = !container.childElementCount;
    },

    removeButton(label, value, key, filterValue) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "active-filter";
      button.textContent = `${label}: ${value} ×`;
      button.setAttribute("aria-label", `Remove ${label} filter ${value}`);
      button.addEventListener("click", () => {
        if (key === "query") {
          this.query = "";
          this.$root.querySelector("[data-search]").value = "";
        } else {
          this.filters[key] = (this.filters[key] || []).filter(item => item !== filterValue);
        }
        this.apply();
      });
      return button;
    },

    toggleComparison(event) {
      const key = event.currentTarget.closest("[data-catalogue-item]").dataset.key;
      if (this.comparison.includes(key)) {
        this.comparison = this.comparison.filter(item => item !== key);
      } else if (this.comparison.length < this.compareMax) {
        this.comparison = [...this.comparison, key];
      } else {
        this.$root.querySelector("[data-comparison-label]").textContent = `${this.compareMax}-model comparison limit reached`;
        return;
      }
      this.updateComparison();
      this.writeUrl();
    },

    updateComparison() {
      for (const button of this.$root.querySelectorAll("[data-compare-toggle]")) {
        const key = button.closest("[data-catalogue-item]").dataset.key;
        const selected = this.comparison.includes(key);
        button.setAttribute("aria-pressed", String(selected));
        button.textContent = selected ? "Selected" : "Compare";
      }
      const count = this.comparison.length;
      this.$root.querySelector("[data-comparison-tray]").hidden = count === 0;
      this.$root.querySelector("[data-comparison-label]").textContent = `${count} ${count === 1 ? "model" : "models"} selected`;
      for (const button of this.$root.querySelectorAll("[data-open-comparison]")) button.disabled = count < 2;
      for (const counter of this.$root.querySelectorAll("[data-comparison-count]")) counter.textContent = String(count);
    },

    openComparison() {
      if (this.comparison.length < 2) return;
      const selected = this.comparison.map(key => this.cards.find(card => card.element.dataset.key === key).element);
      const table = document.createElement("table");
      table.className = "comparison-table";
      table.append(this.comparisonHead(selected), this.comparisonBody(selected));
      const content = this.$root.querySelector("[data-comparison-content]");
      content.replaceChildren(table);
      const dialog = this.$root.querySelector("[data-comparison-dialog]");
      typeof dialog.showModal === "function" ? dialog.showModal() : dialog.setAttribute("open", "");
    },

    comparisonHead(selected) {
      const head = document.createElement("thead");
      const row = document.createElement("tr");
      const field = document.createElement("th");
      field.scope = "col";
      field.textContent = "Field";
      row.append(field);
      for (const model of selected) {
        const cell = document.createElement("th");
        cell.scope = "col";
        const link = document.createElement("a");
        link.href = model.dataset.modelUrl;
        link.textContent = model.dataset.modelName;
        cell.append(link);
        row.append(cell);
      }
      head.append(row);
      return head;
    },

    comparisonBody(selected) {
      const body = document.createElement("tbody");
      const fields = [["Identifier", "modelId"], ["Vendor", "vendor"], ["Context window", "compareContext"], ["Capabilities", "compareCapabilities"], ["Modalities", "compareModalities"], ["Licence", "compareLicence"], ["Lifecycle", "compareLifecycle"]];
      for (const [label, key] of fields) {
        const row = document.createElement("tr");
        const heading = document.createElement("th");
        heading.scope = "row";
        heading.textContent = label;
        row.append(heading);
        for (const model of selected) {
          const cell = document.createElement("td");
          cell.textContent = model.dataset[key] || "Not stated";
          row.append(cell);
        }
        body.append(row);
      }
      return body;
    },

    closeComparison() {
      const dialog = this.$root.querySelector("[data-comparison-dialog]");
      dialog.open && typeof dialog.close === "function" ? dialog.close() : dialog.removeAttribute("open");
    },
  }));

  window.Alpine.data("macBuilder", () => ({
    operation: "add",
    subjectKind: "model",
    subjectIdentity: "",
    purpose: "",
    outcome: "",
    reason: "",
    candidateEvidence: "",
    acceptance: "",
    githubLink: "",
    yamlOutput: "",
    webBase: "",

    init() {
      const form = this.$root;
      this.webBase = form ? (form.dataset.webBase || "https://github.com/j3brns996/Modelo") : "https://github.com/j3brns996/Modelo";
      const opElem = form.querySelector('[data-field="operation"]');
      if (opElem) this.operation = opElem.value || "add";
      const kindElem = form.querySelector('[data-field="subject-kind"]');
      if (kindElem) this.subjectKind = kindElem.value || "model";
      const idElem = form.querySelector('[data-field="subject-identity"]');
      if (idElem) this.subjectIdentity = idElem.value || "";
      const purpElem = form.querySelector('[data-field="purpose"]');
      if (purpElem) this.purpose = purpElem.value || "";
      const outElem = form.querySelector('[data-field="outcome"]');
      if (outElem) this.outcome = outElem.value || "";
      const reasElem = form.querySelector('[data-field="reason"]');
      if (reasElem) this.reason = reasElem.value || "";
      const evElem = form.querySelector('[data-field="candidate-evidence"]');
      if (evElem) this.candidateEvidence = evElem.value || "";
      const accElem = form.querySelector('[data-field="acceptance"]');
      if (accElem) this.acceptance = accElem.value || "";

      form.addEventListener("submit", event => event.preventDefault());
      this.update();
    },

    update() {
      const form = this.$root;
      if (form) {
        const opElem = form.querySelector('[data-field="operation"]');
        if (opElem) this.operation = opElem.value;
        const kindElem = form.querySelector('[data-field="subject-kind"]');
        if (kindElem) this.subjectKind = kindElem.value;
        const idElem = form.querySelector('[data-field="subject-identity"]');
        if (idElem) this.subjectIdentity = idElem.value;
        const purpElem = form.querySelector('[data-field="purpose"]');
        if (purpElem) this.purpose = purpElem.value;
        const outElem = form.querySelector('[data-field="outcome"]');
        if (outElem) this.outcome = outElem.value;
        const reasElem = form.querySelector('[data-field="reason"]');
        if (reasElem) this.reason = reasElem.value;
        const evElem = form.querySelector('[data-field="candidate-evidence"]');
        if (evElem) this.candidateEvidence = evElem.value;
        const accElem = form.querySelector('[data-field="acceptance"]');
        if (accElem) this.acceptance = accElem.value;
      }

      const parameters = new URLSearchParams();
      parameters.set("template", `mac-${this.operation || "add"}.yml`);
      if (this.subjectKind) parameters.set("subject_kind", this.subjectKind);
      if (this.subjectIdentity) parameters.set("subject_identity", this.subjectIdentity);
      if (this.purpose) parameters.set("purpose", this.purpose);
      if (this.outcome) parameters.set("requested_outcome", this.outcome);
      if (this.reason) parameters.set("reason", this.reason);
      if (this.candidateEvidence) parameters.set("candidate_evidence", this.candidateEvidence);
      if (this.acceptance) parameters.set("acceptance", this.acceptance);

      const base = (this.webBase || "https://github.com/j3brns996/Modelo").replace(/\/+$/, "");
      this.githubLink = `${base}/issues/new?${parameters.toString()}`;

      if (form) {
        const linkElem = form.querySelector("[data-github-issue-link]");
        if (linkElem) linkElem.setAttribute("href", this.githubLink);
      }

      this.yamlOutput = this.generateYaml();
      if (form) {
        const yamlElem = form.querySelector("[data-mac-yaml]");
        if (yamlElem) yamlElem.value = this.yamlOutput;
      }
    },

    generateYaml() {
      const op = this.operation || "add";
      const kind = this.subjectKind || "model";
      const identity = this.subjectIdentity || "";
      const purp = this.purpose || "";
      const outc = this.outcome || "";
      const reas = this.reason || "";
      const evText = this.candidateEvidence || "";
      const accText = this.acceptance || "";

      const lines = [
        'schema_version: "0.1"',
        `operation: ${op}`,
        `purpose: ${JSON.stringify(purp)}`,
        'subjects:',
        `  - kind: ${kind}`,
        `    identity: ${JSON.stringify(identity)}`,
        `requested_outcome: ${JSON.stringify(outc)}`,
        `reason: ${JSON.stringify(reas)}`,
        'candidate_evidence:'
      ];

      const evLines = evText.split("\n").map(l => l.trim()).filter(Boolean);
      if (evLines.length === 0) {
        lines.push('  []');
      } else {
        for (const line of evLines) {
          const parts = line.split("|").map(p => p.trim());
          if (parts.length >= 3) {
            lines.push(`  - uri: ${JSON.stringify(parts[0])}`);
            lines.push(`    observed_at: ${JSON.stringify(parts[1])}`);
            lines.push(`    digest: ${JSON.stringify(parts[2])}`);
          } else {
            lines.push(`  - uri: ${JSON.stringify(line)}`);
          }
        }
      }

      lines.push('acceptance:');
      const accLines = accText.split("\n").map(l => l.trim()).filter(Boolean);
      if (accLines.length === 0) {
        lines.push('  []');
      } else {
        for (const line of accLines) {
          lines.push(`  - ${JSON.stringify(line)}`);
        }
      }

      return lines.join("\n");
    },

    copyYaml() {
      const text = this.yamlOutput || this.generateYaml();
      if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
        navigator.clipboard.writeText(text);
      } else if (this.$root) {
        const yamlElem = this.$root.querySelector("[data-mac-yaml]");
        if (yamlElem) {
          yamlElem.select();
          document.execCommand("copy");
        }
      }
      if (this.$root) {
        const label = this.$root.querySelector("[data-copy-label]");
        if (label) {
          const orig = label.textContent;
          label.textContent = "Copied!";
          setTimeout(() => { label.textContent = orig; }, 2000);
        }
      }
    }
  }));
});

function initMacBuilderVanilla() {
  const forms = document.querySelectorAll("form[data-mac-builder]");
  for (const form of forms) {
    if (form.dataset.macBuilderInitialized) continue;
    form.dataset.macBuilderInitialized = "true";

    const update = () => {
      const webBase = (form.dataset.webBase || "https://github.com/j3brns996/Modelo").replace(/\/+$/, "");
      const op = (form.querySelector('[data-field="operation"]')?.value || "add").trim();
      const kind = (form.querySelector('[data-field="subject-kind"]')?.value || "model").trim();
      const identity = (form.querySelector('[data-field="subject-identity"]')?.value || "").trim();
      const purpose = (form.querySelector('[data-field="purpose"]')?.value || "").trim();
      const outcome = (form.querySelector('[data-field="outcome"]')?.value || "").trim();
      const reason = (form.querySelector('[data-field="reason"]')?.value || "").trim();
      const evidence = (form.querySelector('[data-field="candidate-evidence"]')?.value || "").trim();
      const acceptance = (form.querySelector('[data-field="acceptance"]')?.value || "").trim();

      const params = new URLSearchParams();
      params.set("template", `mac-${op}.yml`);
      if (kind) params.set("subject_kind", kind);
      if (identity) params.set("subject_identity", identity);
      if (purpose) params.set("purpose", purpose);
      if (outcome) params.set("requested_outcome", outcome);
      if (reason) params.set("reason", reason);
      if (evidence) params.set("candidate_evidence", evidence);
      if (acceptance) params.set("acceptance", acceptance);

      const linkElem = form.querySelector("[data-github-issue-link]");
      if (linkElem) {
        linkElem.setAttribute("href", `${webBase}/issues/new?${params.toString()}`);
      }

      const lines = [
        'schema_version: "0.1"',
        `operation: ${op}`,
        `purpose: ${JSON.stringify(purpose)}`,
        'subjects:',
        `  - kind: ${kind}`,
        `    identity: ${JSON.stringify(identity)}`,
        `requested_outcome: ${JSON.stringify(outcome)}`,
        `reason: ${JSON.stringify(reason)}`,
        'candidate_evidence:'
      ];

      const evLines = evidence.split("\n").map(l => l.trim()).filter(Boolean);
      if (evLines.length === 0) {
        lines.push('  []');
      } else {
        for (const line of evLines) {
          const parts = line.split("|").map(p => p.trim());
          if (parts.length >= 3) {
            lines.push(`  - uri: ${JSON.stringify(parts[0])}`);
            lines.push(`    observed_at: ${JSON.stringify(parts[1])}`);
            lines.push(`    digest: ${JSON.stringify(parts[2])}`);
          } else {
            lines.push(`  - uri: ${JSON.stringify(line)}`);
          }
        }
      }

      lines.push('acceptance:');
      const accLines = acceptance.split("\n").map(l => l.trim()).filter(Boolean);
      if (accLines.length === 0) {
        lines.push('  []');
      } else {
        for (const line of accLines) {
          lines.push(`  - ${JSON.stringify(line)}`);
        }
      }

      const yamlElem = form.querySelector("[data-mac-yaml]");
      if (yamlElem) {
        yamlElem.value = lines.join("\n");
      }
    };

    form.addEventListener("submit", event => event.preventDefault());
    form.addEventListener("input", update);
    form.addEventListener("change", update);

    const copyBtn = form.querySelector("[data-copy-yaml]");
    if (copyBtn) {
      copyBtn.addEventListener("click", () => {
        const yamlElem = form.querySelector("[data-mac-yaml]");
        const text = yamlElem ? yamlElem.value : "";
        if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
          navigator.clipboard.writeText(text);
        } else if (yamlElem) {
          yamlElem.select();
          document.execCommand("copy");
        }
        const label = form.querySelector("[data-copy-label]");
        if (label) {
          const orig = label.textContent;
          label.textContent = "Copied!";
          setTimeout(() => { label.textContent = orig; }, 2000);
        }
      });
    }

    update();
  }
}

if (typeof document !== "undefined" && typeof document.querySelectorAll === "function") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMacBuilderVanilla);
  } else {
    initMacBuilderVanilla();
  }
}
