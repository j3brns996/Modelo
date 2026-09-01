"use strict";

document.addEventListener("alpine:init", () => {
  window.Alpine.data("catalogueExplorer", () => ({
    query: "",
    filters: {},
    sort: "name-asc",
    view: "grid",
    comparison: [],
    rows: [],
    filterButtons: [],
    searchMax: 200,
    compareMax: 4,
    viewStorageKey: "",
    defaultView: "grid",

    init() {
      this.rows = [...this.$root.querySelectorAll("[data-catalogue-row]")].map((element, index) => ({ element, index }));
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
      const modelKeys = new Set(this.rows.filter(row => row.element.dataset.kind === "model").map(row => row.element.dataset.key));
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
      this.query = event.currentTarget.value.toLocaleLowerCase("en-GB").trim().slice(0, this.searchMax);
      this.apply();
    },

    toggleFilter(event) {
      const button = event.currentTarget;
      const key = button.dataset.filter;
      const value = button.dataset.value;
      const selected = new Set(this.filters[key] || []);
      selected.has(value) ? selected.delete(value) : selected.add(value);
      this.filters[key] = [...selected];
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
      const ordered = [...this.rows].sort((left, right) => this.compareRows(left, right));
      let visible = 0;
      for (const row of ordered) {
        row.element.hidden = !this.matches(row);
        if (!row.element.hidden) visible += 1;
        body.append(row.element);
      }
      const total = this.rows.length;
      this.$root.querySelector("[data-result-count]").textContent = `Showing ${visible} of ${total} ${total === 1 ? "record" : "records"}`;
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
      const key = event.currentTarget.closest("[data-catalogue-row]").dataset.key;
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
        const key = button.closest("[data-catalogue-row]").dataset.key;
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
      const selected = this.comparison.map(key => this.rows.find(row => row.element.dataset.key === key).element);
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
});
