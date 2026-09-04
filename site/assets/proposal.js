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

    const identityPattern = /^[a-z0-9](?:[a-z0-9._:/@+-]*[a-z0-9])?$/;

    const update = () => {
      const operation = value("operation") === "change" ? "change" : "add";
      const configuredUrl = operation === "change" ? form.dataset.intakeChange : form.dataset.intakeAdd;
      const url = new URL(configuredUrl);
      const identity = value("subject-identity");
      const purpose = value("purpose");
      const outcome = value("outcome");
      const reason = value("reason");
      const candidateEvidence = value("candidate-evidence");
      const acceptance = value("acceptance");

      let statusMsg = "";
      if (identity && !identityPattern.test(identity)) {
        statusMsg = "Subject identity must be lowercase ASCII (e.g. aws-bedrock-nova-lite).";
      }

      const fields = [
        ["subject_kind", value("subject-kind")],
        ["subject_identity", identity],
        ["purpose", purpose],
        ["requested_outcome", outcome],
        ["reason", reason],
        ["candidate_evidence", candidateEvidence],
        ["acceptance", acceptance],
      ];
      for (const [name, content] of fields) {
        content ? url.searchParams.set(name, content) : url.searchParams.delete(name);
      }
      issueLink.href = url.toString();
      summary.value = [
        `Operation: ${operation}`,
        `Subject kind: ${value("subject-kind")}`,
        `Subject identity: ${identity}${statusMsg ? ` (Warning: ${statusMsg})` : ""}`,
        `Purpose: ${purpose}`,
        `Requested outcome: ${outcome}`,
        `Why needed: ${reason}`,
        "Candidate evidence:",
        candidateEvidence,
        "Acceptance checks:",
        acceptance,
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
