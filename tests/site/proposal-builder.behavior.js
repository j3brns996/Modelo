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
  ["candidate-evidence", "https://docs.example.invalid/alpha | 2026-09-05T09:00:00Z | sha256-alpha"],
  ["acceptance", "Evidence matches"],
]) fields.set(name, control(value));

const summary = control();
summary.selected = false;
summary.select = () => { summary.selected = true; };
const issueLink = { href: "" };
const urlStatus = { textContent: "" };
const copyStatus = { textContent: "" };
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
      "[data-proposal-url-status]": urlStatus,
      "[data-proposal-copy-status]": copyStatus,
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
const template = fs.readFileSync(path.join(__dirname, "../../site/templates/propose.html"), "utf8");
assert.match(template, /data-copy-summary><span>Copy draft summary<\/span>/);
assert.doesNotMatch(template, /data-copy-label/);
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
  assert.equal(urlStatus.textContent, "Issue form link updated with the draft fields.");
  assert.equal(copyStatus.textContent, "");
  assert.match(summary.value, /^Operation: add/m);
  assert.match(summary.value, /Subject identity: alpha-model/);
  assert.doesNotMatch(summary.value, /Warning:/);
  assert.doesNotMatch(summary.value, /schema_version|YAML|subjects:/);
}

// Invalid identities remain visible and pre-filled, with the PR #63 warning retained.
{
  fields.get("subject-identity").value = "Bad Identity";
  formListeners.get("input")();
  const url = new URL(issueLink.href);
  assert.equal(url.searchParams.get("subject_identity"), "Bad Identity");
  assert.match(summary.value, /Subject identity: Bad Identity \(Warning: Subject identity must be lowercase ASCII/);
  fields.get("subject-identity").value = "alpha-model";
  formListeners.get("input")();
  assert.doesNotMatch(summary.value, /Warning:/);
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

// The length bound is inclusive and is applied to the final percent-encoded href.
{
  fields.get("operation").value = "add";
  for (const name of ["subject-kind", "subject-identity", "purpose", "outcome", "reason", "candidate-evidence", "acceptance"]) {
    fields.get(name).value = "";
  }
  formListeners.get("input")();
  const configuredLength = form.dataset.intakeAdd.length;
  fields.get("reason").value = "x".repeat(7000 - configuredLength - "&reason=".length);
  formListeners.get("input")();
  assert.equal(issueLink.href.length, 7000);
  assert.equal(new URL(issueLink.href).searchParams.get("reason"), fields.get("reason").value);
  assert.equal(urlStatus.textContent, "Issue form link updated with the draft fields.");

  fields.get("reason").value += "x";
  const completeBoundaryReason = fields.get("reason").value;
  formListeners.get("input")();
  assert.equal(issueLink.href, form.dataset.intakeAdd);
  assert.equal(new URL(issueLink.href).searchParams.has("reason"), false);
  assert.equal(summary.value.includes(completeBoundaryReason), true);
}

// A short raw value whose percent-encoded href exceeds the bound also falls back atomically.
{
  fields.get("operation").value = "change";
  fields.get("reason").value = "€".repeat(800);
  const completeReason = fields.get("reason").value;
  const encodedCandidate = new URL(form.dataset.intakeChange);
  encodedCandidate.searchParams.set("reason", completeReason);
  assert.equal(completeReason.length, 800);
  assert.equal(encodedCandidate.href.length > 7000, true);
  formListeners.get("change")();
  assert.equal(issueLink.href, form.dataset.intakeChange);
  const fallback = new URL(issueLink.href);
  assert.equal(fallback.searchParams.get("template"), "configured-change");
  assert.equal(fallback.searchParams.get("kept"), "yes");
  for (const userParam of ["subject_kind", "subject_identity", "purpose", "requested_outcome", "reason", "candidate_evidence", "acceptance"]) {
    assert.equal(fallback.searchParams.has(userParam), false);
  }
  assert.match(urlStatus.textContent, /too long to pre-fill safely/);
  assert.match(urlStatus.textContent, /complete draft summary/);
  assert.equal(copyStatus.textContent, "");
  assert.equal(summary.value.includes(completeReason), true);
}

(async () => {
  const click = copyButton.listeners.get("click");

  // Success is reported only after the clipboard promise resolves.
  let resolveWrite;
  navigator.clipboard.writeText = () => new Promise(resolve => { resolveWrite = resolve; });
  const success = click();
  assert.equal(copyStatus.textContent, "");
  const overflowAnnouncement = urlStatus.textContent;
  resolveWrite();
  await success;
  assert.equal(copyStatus.textContent, "Draft summary copied.");
  assert.equal(urlStatus.textContent, overflowAnnouncement);

  // Rejection never produces a success claim and selects a truthful manual fallback.
  summary.selected = false;
  navigator.clipboard.writeText = async () => { throw new Error("denied"); };
  await click();
  assert.equal(copyStatus.textContent, "Copy failed. Select the draft summary and copy it manually.");
  assert.equal(summary.selected, true);
  assert.equal(urlStatus.textContent, overflowAnnouncement);

  // Missing Clipboard API also exposes only the manual action.
  summary.selected = false;
  navigator.clipboard = undefined;
  await click();
  assert.equal(copyStatus.textContent, "Select and copy manually");
  assert.equal(summary.selected, true);
  assert.equal(urlStatus.textContent, overflowAnnouncement);

  console.log("proposal builder behavior: passed");
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
