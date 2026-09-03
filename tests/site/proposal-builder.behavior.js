"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const documentListeners = new Map();
const fields = new Map();
const formListeners = new Map();

function control(value = "") {
  return {
    value,
    listeners: new Map(),
    addEventListener(name, callback) { this.listeners.set(name, callback); },
  };
}

for (const [name, value] of [
  ["operation", "add"],
  ["subject-kind", "model"],
  ["subject-identity", "alpha-model"],
  ["purpose", "Evaluate alpha"],
  ["outcome", "Add a reviewed model"],
  ["reason", "A team needs it"],
  ["candidate-evidence", "https://docs.example.invalid/alpha"],
  ["acceptance", "Evidence matches"],
]) fields.set(name, control(value));

const summary = control();
summary.selected = false;
summary.select = () => { summary.selected = true; };
const issueLink = { href: "" };
const copyLabel = { textContent: "Copy draft summary" };
const copyButton = control();

const form = {
  dataset: {
    intakeAdd: "https://code.example.invalid/group/catalogue/new?template=configured-add",
    intakeChange: "https://code.example.invalid/group/catalogue/edit?template=configured-change&kept=yes",
  },
  querySelector(selector) {
    const fieldMatch = selector.match(/^\[data-field="([^"]+)"\]$/);
    if (fieldMatch) return fields.get(fieldMatch[1]);
    return {
      "[data-proposal-summary]": summary,
      "[data-proposal-issue-link]": issueLink,
      "[data-copy-summary]": copyButton,
      "[data-copy-label]": copyLabel,
    }[selector] || null;
  },
  addEventListener(name, callback) { formListeners.set(name, callback); },
};

global.document = {
  readyState: "loading",
  querySelectorAll(selector) {
    return selector === "form[data-proposal-builder]" ? [form] : [];
  },
  addEventListener(name, callback) { documentListeners.set(name, callback); },
};
Object.defineProperty(global, "navigator", {
  value: { clipboard: { writeText: async () => {} } },
  configurable: true,
});

const source = fs.readFileSync(path.join(__dirname, "../../site/assets/proposal.js"), "utf8");
vm.runInThisContext(source, { filename: "proposal.js" });
assert.equal(typeof documentListeners.get("DOMContentLoaded"), "function");
documentListeners.get("DOMContentLoaded")();
assert.equal(form.dataset.proposalBuilderInitialized, "true");
assert.equal(formListeners.has("input"), true);
assert.equal(formListeners.has("change"), true);
assert.equal(copyButton.listeners.has("click"), true);

// The controller extends the exact configured route; it does not rebuild host, path or template.
{
  const url = new URL(issueLink.href);
  assert.equal(url.origin + url.pathname, "https://code.example.invalid/group/catalogue/new");
  assert.equal(url.searchParams.get("template"), "configured-add");
  assert.equal(url.searchParams.get("subject_identity"), "alpha-model");
  assert.match(summary.value, /^Operation: add/m);
  assert.match(summary.value, /Subject identity: alpha-model/);
  assert.doesNotMatch(summary.value, /schema_version|YAML|subjects:/);
}

// Only the supported selector value changes the configured intake base URL.
{
  fields.get("operation").value = "change";
  formListeners.get("change")();
  const url = new URL(issueLink.href);
  assert.equal(url.origin + url.pathname, "https://code.example.invalid/group/catalogue/edit");
  assert.equal(url.searchParams.get("template"), "configured-change");
  assert.equal(url.searchParams.get("kept"), "yes");
  assert.equal(url.searchParams.get("purpose"), "Evaluate alpha");
}

(async () => {
  const click = copyButton.listeners.get("click");

  // Success is reported only after the clipboard promise resolves.
  let resolveWrite;
  navigator.clipboard.writeText = () => new Promise(resolve => { resolveWrite = resolve; });
  const success = click();
  assert.equal(copyLabel.textContent, "Copy draft summary");
  resolveWrite();
  await success;
  assert.equal(copyLabel.textContent, "Copied");

  // Rejection never produces a success claim and selects a truthful manual fallback.
  summary.selected = false;
  navigator.clipboard.writeText = async () => { throw new Error("denied"); };
  await click();
  assert.equal(copyLabel.textContent, "Copy failed — select text manually");
  assert.equal(summary.selected, true);

  // Missing Clipboard API also exposes only the manual action.
  summary.selected = false;
  navigator.clipboard = undefined;
  await click();
  assert.equal(copyLabel.textContent, "Select and copy manually");
  assert.equal(summary.selected, true);

  console.log("proposal builder behavior: passed");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
