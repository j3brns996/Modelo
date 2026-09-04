"use strict";

function initProposalBuilder() {
  for (const form of document.querySelectorAll("form[data-proposal-builder]")) {
    if (form.dataset.proposalBuilderInitialized) continue;
    form.dataset.proposalBuilderInitialized = "true";

    const field = name => form.querySelector(`[data-field="${name}"]`);
    const value = name => (field(name)?.value || "").trim();
    const summary = form.querySelector("[data-proposal-summary]");
    const issueLink = form.querySelector("[data-proposal-issue-link]");
    const copyButton = form.querySelector("[data-copy-summary]");
    const copyLabel = form.querySelector("[data-copy-label]");

    const update = () => {
      const operation = value("operation") === "change" ? "change" : "add";
      const configuredUrl = operation === "change" ? form.dataset.intakeChange : form.dataset.intakeAdd;
      const url = new URL(configuredUrl);
      const fields = [
        ["subject_kind", value("subject-kind")],
        ["subject_identity", value("subject-identity")],
        ["purpose", value("purpose")],
        ["requested_outcome", value("outcome")],
        ["reason", value("reason")],
        ["candidate_evidence", value("candidate-evidence")],
        ["acceptance", value("acceptance")],
      ];
      for (const [name, content] of fields) {
        content ? url.searchParams.set(name, content) : url.searchParams.delete(name);
      }
      issueLink.href = url.toString();
      summary.value = [
        `Operation: ${operation}`,
        `Subject kind: ${value("subject-kind")}`,
        `Subject identity: ${value("subject-identity")}`,
        `Purpose: ${value("purpose")}`,
        `Requested outcome: ${value("outcome")}`,
        `Why needed: ${value("reason")}`,
        "Candidate evidence:",
        value("candidate-evidence"),
        "Acceptance checks:",
        value("acceptance"),
      ].join("\n");
    };

    const manualCopy = message => {
      summary.select();
      copyLabel.textContent = message;
    };
    copyButton.addEventListener("click", async () => {
      if (!navigator.clipboard || typeof navigator.clipboard.writeText !== "function") {
        manualCopy("Select and copy manually");
        return;
      }
      try {
        await navigator.clipboard.writeText(summary.value);
        copyLabel.textContent = "Copied";
      } catch (_error) {
        manualCopy("Copy failed — select text manually");
      }
    });
    form.addEventListener("submit", event => event.preventDefault());
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    update();
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initProposalBuilder);
} else {
  initProposalBuilder();
}
