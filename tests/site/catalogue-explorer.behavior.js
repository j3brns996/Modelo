"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

let alpineInitialiser;
let componentFactory;
const stored = new Map();

global.document = {
  addEventListener(name, callback) {
    if (name === "alpine:init") alpineInitialiser = callback;
  },
  createElement() {
    return new FakeElement();
  },
};

global.window = {
  Alpine: {
    data(name, factory) {
      if (name === "catalogueExplorer") {
        componentFactory = factory;
      }
    },
  },
  location: new URL("https://example.invalid/Modelo/catalogue/"),
  history: {
    replaceState(_state, _title, value) {
      window.location = new URL(value);
    },
  },
  localStorage: {
    getItem(key) {
      return stored.get(key) || null;
    },
    setItem(key, value) {
      stored.set(key, value);
    },
  },
};

class FakeElement {
  constructor(dataset = {}, attributes = {}) {
    this.dataset = dataset;
    this.attributes = new Map(Object.entries(attributes));
    this.children = [];
    this.hidden = false;
    this.textContent = "";
  }

  getAttribute(name) {
    return this.attributes.get(name) || "";
  }

  setAttribute(name, value) {
    this.attributes.set(name, value);
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }
}

const source = fs.readFileSync(path.join(__dirname, "../../site/assets/catalogue.js"), "utf8");
vm.runInThisContext(source, { filename: "catalogue.js" });
assert.equal(typeof alpineInitialiser, "function");
alpineInitialiser();
assert.equal(typeof componentFactory, "function");

function component() {
  const value = componentFactory();
  value.searchMax = 200;
  value.compareMax = 4;
  value.viewStorageKey = "modelo.catalogue.view.v1";
  value.defaultView = "grid";
  return value;
}

function record(index, { key, name, kind, search, facets = {} }) {
  const attributes = {};
  for (const [facet, values] of Object.entries(facets)) attributes[`data-${facet}`] = values.join("|");
  return {
    index,
    element: new FakeElement(
      { key, name, kind, searchText: search },
      attributes,
    ),
  };
}

// Search and facet semantics: OR within a facet, AND across facets.
{
  const explorer = component();
  const model = record(0, {
    key: "model:alpha", name: "Alpha", kind: "model",
    search: "alpha|vendor-a|chat", facets: { vendor: ["vendor-a"], capability: ["chat"] },
  });
  explorer.query = "ALPHA";
  explorer.filters = { vendor: ["vendor-a", "vendor-b"], capability: ["chat"] };
  assert.equal(explorer.matches(model), true);
  explorer.filters.capability = ["vision"];
  assert.equal(explorer.matches(model), false);
  explorer.query = "compare";
  explorer.filters = {};
  assert.equal(explorer.matches(model), false, "control labels must not enter semantic search");
}

// Alpine debounce may clear currentTarget before invoking the handler.
{
  const explorer = component();
  explorer.apply = () => {};
  explorer.searchChanged({ target: { value: "  Nova Micro  " }, currentTarget: null });
  assert.equal(explorer.query, "nova micro");
}

// Offerings live in the complete table, so selecting that filter changes view.
{
  const explorer = component();
  explorer.filters = { kind: [] };
  explorer.view = "grid";
  explorer.apply = () => {};
  explorer.writeViewPreference = () => {};
  explorer.toggleFilter({ currentTarget: { dataset: { filter: "kind", value: "offering" } } });
  assert.equal(explorer.view, "table");
  assert.deepEqual(explorer.filters.kind, ["offering"]);
}

// Deterministic sort and visibility application use the actual controller.
{
  const explorer = component();
  const alpha = record(1, { key: "model:alpha", name: "Alpha 2", kind: "model", search: "alpha" });
  const beta = record(0, { key: "offering:beta", name: "Beta 10", kind: "offering", search: "beta" });
  const body = new FakeElement();
  const grid = new FakeElement();
  const result = new FakeElement();
  const empty = new FakeElement();
  explorer.rows = [beta, alpha];
  explorer.cards = [alpha];
  explorer.filters = {};
  explorer.query = "alpha";
  explorer.sort = "name-asc";
  explorer.view = "grid";
  explorer.filterButtons = [];
  explorer.renderActiveFilters = () => {};
  explorer.writeUrl = () => {};
  explorer.$root = {
    dataset: {},
    querySelector(selector) {
      return { "[data-catalogue-body]": body, "[data-catalogue-grid]": grid, "[data-result-count]": result, "[data-no-results]": empty }[selector];
    },
    querySelectorAll() {
      return [];
    },
  };
  explorer.apply(false);
  assert.deepEqual(grid.children, [alpha.element]);
  assert.equal(alpha.element.hidden, false);
  assert.equal(result.textContent, "Showing 1 of 1 model");
  assert.equal(explorer.$root.dataset.view, "grid");
}

// URL state is bounded, repeatable and preserves parameters it does not own.
{
  const explorer = component();
  explorer.query = "alpha";
  explorer.filters = { vendor: ["vendor-b", "vendor-a"] };
  explorer.filterButtons = [{ dataset: { filter: "vendor" } }];
  explorer.sort = "models-first";
  explorer.view = "grid";
  explorer.comparison = ["model:alpha", "model:beta"];
  window.location = new URL("https://example.invalid/Modelo/catalogue/?unowned=kept");
  explorer.writeUrl();
  assert.equal(window.location.searchParams.get("unowned"), "kept");
  assert.deepEqual(window.location.searchParams.getAll("vendor"), ["vendor-a", "vendor-b"]);
  assert.deepEqual(window.location.searchParams.getAll("compare"), ["model:alpha", "model:beta"]);
  assert.equal(window.location.searchParams.get("view"), null);
}

// A valid URL view wins over local preference; unavailable storage fails safe.
{
  const explorer = component();
  stored.set(explorer.viewStorageKey, "grid");
  assert.equal(explorer.readViewPreference(new URLSearchParams("view=table")), "table");
  assert.equal(explorer.readViewPreference(new URLSearchParams()), "grid");
  const available = window.localStorage;
  window.localStorage = { getItem() { throw new Error("blocked"); }, setItem() { throw new Error("blocked"); } };
  assert.equal(explorer.readViewPreference(new URLSearchParams()), "grid");
  explorer.view = "table";
  explorer.apply = () => {};
  assert.doesNotThrow(() => explorer.changeView({ currentTarget: { dataset: { view: "grid" } } }));
  window.localStorage = available;
}

// Comparison is canonical-model-only upstream and bounded to four here.
{
  const explorer = component();
  const label = new FakeElement();
  explorer.$root = { querySelector() { return label; } };
  explorer.comparison = ["model:a", "model:b", "model:c", "model:d"];
  const event = { currentTarget: { closest() { return { dataset: { key: "model:e" } }; } } };
  explorer.toggleComparison(event);
  assert.deepEqual(explorer.comparison, ["model:a", "model:b", "model:c", "model:d"]);
  assert.equal(label.textContent, "4-model comparison limit reached");
}

console.log("catalogue explorer behavior: passed");
