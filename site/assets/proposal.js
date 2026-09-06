"use strict";

const PROPOSAL_URL_MAX_LENGTH = 7000;
const PROPOSAL_OPERATIONS = {
  add: "Add a new record. Choose an unused ID and explain what should be recorded.",
  change: "Update an existing record. Its identity stays the same; describe the facts that should change.",
  revoke: "Withdraw one offering. Explain the decision to end access; missing discovery results alone are not a reason.",
  move: "Replace an offering. Choose the current ID and a new replacement ID. Both changes are reviewed together.",
  batch: "Make up to 25 related changes. Every record must share the operation, source, observation scope and service.",
};

function proposalTitle(fields) {
  const operation = fields.find(field => field.name === "request_type").value;
  const identity = fields.find(field => ["subject_identity", "offering_identity", "source_identity", "subject_identities"].includes(field.name));
  return `${operation[0].toUpperCase()}${operation.slice(1)}: ${identity?.value.split("\n")[0] || "Catalogue proposal"}`.slice(0, 255);
}

function proposalMarkdown(fields) {
  const guide = fields.filter(field => field.help).map(field => `**${field.label}:** ${field.help}`).join("\n\n");
  return `# ${proposalTitle(fields)}\n\n` + (guide ? `## Field guide\n\n${guide}\n\n## Your answers\n\n` : "") + fields.map(field => `### ${field.label}\n\n${field.value || "_No response_"}`).join("\n\n")
    + "\n\n### Before submitting\n\n- [ ] I checked for existing records and requests.\n"
    + "- [ ] I have not included credentials, tokens or private commercial terms.\n"
    + "- [ ] I understand that this request is not approval.\n";
}

function proposalURL(configured, provider, fields, markdown, title = proposalTitle(fields)) {
  const url = new URL(configured);
  if (provider === "gitlab") {
    url.searchParams.delete("issuable_template");
    url.searchParams.delete("description_template");
    url.searchParams.set("issue[title]", title);
    url.searchParams.set("issue[description]", markdown);
    url.searchParams.set("issue[issue_type]", "issue");
  } else if (provider === "github") {
    url.searchParams.set("title", title);
    for (const field of fields) {
      const name = field.name === "offering_identity" ? "subject_identity" : field.name;
      field.value ? url.searchParams.set(name, field.value) : url.searchParams.delete(name);
    }
  } else throw new Error("Unsupported proposal provider");
  return {href: url.href.length <= PROPOSAL_URL_MAX_LENGTH ? url.href : configured,
    overflow: url.href.length > PROPOSAL_URL_MAX_LENGTH};
}

function proposalErrors(fields, records) {
  const errors = {};
  const values = Object.fromEntries(fields.map(field => [field.name, field.value]));
  const operation = values.request_type;
  const effective = operation === "batch" ? values.item_operation : operation;
  const identityPattern = /^[a-z0-9](?:[a-z0-9._:/@+\-]*[a-z0-9])?$/;
  const lines = value => value.split("\n").map(line => line.trim()).filter(Boolean);
  for (const field of fields) {
    if (field.required && !field.value) errors[field.name] = "Please complete this field.";
    if (/[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/.test(field.value)
        || /(^|\n)\s*(?:#{1,6}\s|\/\w|```)|<!--|-->/.test(field.value)) {
      errors[field.name] = "Use plain answers here, without headings, hidden comments or GitLab quick actions.";
    }
    if (["purpose", "requested_outcome", "reason", "scope_ref", "partition", "region", "source_url", "model_reference", "need"].includes(field.name)) {
      const limit = field.name === "purpose" ? 160 : (["scope_ref", "partition", "region"].includes(field.name) ? 256 : 2048);
      if (field.value.length > limit) errors[field.name] = `Keep this answer within ${limit} characters.`;
    }
    if (["subject_identity", "offering_identity", "source_identity", "destination_identity", "subject_identities", "inference_service"].includes(field.name)) {
      const ids = lines(field.value);
      if (ids.some(id => !identityPattern.test(id) || id.length > 256)) errors[field.name] = "Use the exact lowercase ID, without spaces (up to 256 characters).";
      if (field.name !== "subject_identities" && ids.length > 1) errors[field.name] = "Enter one ID only.";
      if (ids.length > 25 || new Set(ids).size !== ids.length) errors[field.name] = "Use up to 25 distinct IDs, one per line.";
      const kind = ["offering_identity", "source_identity", "destination_identity"].includes(field.name) ? "offering" : values.subject_kind;
      const creating = field.name === "destination_identity" || (effective === "add" && field.name !== "inference_service");
      if (creating && ids.some(id => records.some(record => record.kind === kind && record.id === id))) errors[field.name] = "That ID is already in this publication. Choose Update for an existing record, or use a distinct new ID.";
    }
  }
  if (operation === "move" && values.source_identity && values.source_identity === values.destination_identity) errors.destination_identity = "The replacement must have a different ID.";
  if (effective === "revoke" && operation === "batch" && values.subject_kind !== "offering") errors.subject_kind = "Withdrawal batches support offerings only.";
  if (values.acceptance && (lines(values.acceptance).length > 25 || lines(values.acceptance).some(line => line.length > 2048))) errors.acceptance = "Use up to 25 checks, each within 2048 characters.";
  const sourceURL = value => /^https:\/\/(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:[/?#][\u0021-\u007e]*)?$/.test(value) && value.length <= 2048;
  if (values.source_url && !sourceURL(values.source_url)) errors.source_url = "Enter an official HTTPS URL without credentials or a port.";
  if (values.candidate_evidence) {
    const observations = lines(values.candidate_evidence);
    if (observations.length > 25 || observations.some(line => {
      const parts = line.split(" | ");
      if (parts.length !== 3) return true;
      const [uri, time, digest] = parts;
      const date = new Date(time);
      return !sourceURL(uri) || !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$/.test(time)
        || !Number.isFinite(date.getTime()) || date.toISOString().slice(0,19) !== time.slice(0,19)
        || !/^sha256-[0-9a-f]{64}$/.test(digest);
    })) errors.candidate_evidence = "Use up to 25 lines: HTTPS URL | UTC time (for example 2026-09-01T09:00:00Z) | sha256- followed by 64 hexadecimal characters.";
  }
  return errors;
}

function modelRequest(reference, need) {
  const fields = [
    {name: "model_reference", label: "Model card or provider", value: reference.trim()},
    {name: "need", label: "What do you need?", value: need.trim(), required: true},
  ];
  const title = `Model request: ${fields[1].value.split("\n")[0] || "Review a model"}`.slice(0, 255);
  const markdown = `# ${title}\n\nA maintainer or agent will prepare any catalogue change. This request is not approval.\n\n`
    + fields.map(field => `### ${field.label}\n\n${field.value || "_No response_"}`).join("\n\n") + "\n";
  return {fields, title, markdown, errors: proposalErrors(fields, [])};
}

async function testRepositoryAccess(configured) {
  try {
    const response = await fetch(configured, {method: "GET", credentials: "include",
      redirect: "manual", cache: "no-store", signal: AbortSignal.timeout(10000)});
    if (response.type === "opaqueredirect" || response.status === 0) return "Could not verify: sign-in or another redirect may be required. Open the repository to continue.";
    if (response.status === 200) return "Repository returned 200. This confirms access to that page, not your login or permission to submit.";
    if (response.status === 403) return "Repository returned 403: access denied. Open the repository to sign in or check your permissions.";
    return `Repository returned ${response.status}. Open the repository to check access.`;
  } catch (_) {
    return "Could not verify access from this page. Open the repository to check access and sign in.";
  }
}

function initModelRequest() {
  for (const form of document.querySelectorAll("form[data-model-request]")) {
    if (form.dataset.initialized) continue;
    form.dataset.initialized = "true";
    const reference = form.querySelector("[data-request-reference]");
    const need = form.querySelector("[data-request-need]");
    const link = form.querySelector("[data-request-link]");
    const summary = form.querySelector("[data-request-summary]");
    const status = form.querySelector("[data-request-status]");
    const copyStatus = form.querySelector("[data-request-copy-status]");
    let checked = false;
    function refresh() {
      const draft = modelRequest(reference.value, need.value);
      summary.value = draft.markdown;
      const result = proposalURL(form.dataset.requestUrl, form.dataset.provider, draft.fields, draft.markdown, draft.title);
      const invalid = Object.keys(draft.errors).length > 0;
      link.href = invalid ? form.dataset.requestUrl : result.href;
      link.setAttribute("aria-disabled", String(invalid));
      for (const [name, input, selector] of [["model_reference", reference, "reference"], ["need", need, "need"]]) {
        const error = checked ? draft.errors[name] : "";
        input.setAttribute("aria-invalid", String(Boolean(error)));
        form.querySelector(`[data-request-${selector}-error]`).textContent = error || "";
      }
      status.textContent = invalid ? "Add a short note about what you need before opening the form."
        : result.overflow ? "This request is too long to prefill. Copy the prepared request and paste its answers into the native form."
        : "Ready to review in the native issue form. Nothing has been submitted.";
      copyStatus.textContent = "";
      return draft.errors;
    }
    form.addEventListener("input", refresh);
    const check = event => {
      checked = true;
      const errors = refresh();
      if (Object.keys(errors).length) {
        event.preventDefault();
        (errors.model_reference ? reference : need).focus();
      }
    };
    link.addEventListener("click", check);
    form.addEventListener("submit", event => {event.preventDefault(); check(event);});
    form.querySelector("[data-request-copy]").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(summary.value);
        copyStatus.textContent = "Request copied. Review it before submitting.";
      } catch (_) {
        summary.closest("details").open = true;
        summary.focus(); summary.select();
        copyStatus.textContent = "Select and copy the request manually.";
      }
    });
    const access = form.querySelector("[data-test-access]");
    if (access) access.addEventListener("click", async () => {
      const result = form.querySelector("[data-access-status]");
      access.disabled = true;
      result.textContent = "Checking repository access...";
      try { result.textContent = await testRepositoryAccess(access.dataset.testAccess); }
      finally { access.disabled = false; }
    });
    refresh(); form.hidden = false;
  }
}

function initProposalBuilder() {
  for (const form of document.querySelectorAll("form[data-proposal-builder]")) {
    if (form.dataset.proposalBuilderInitialized) continue;
    form.dataset.proposalBuilderInitialized = "true";
    const records = JSON.parse(form.dataset.records);
    const groups = [...form.querySelectorAll("[data-operations]")];
    const field = name => form.querySelector(`[data-field="${name}"]`);
    const value = name => field(name).value.trim();
    const initialOperation = new URL(window.location.href).searchParams.get("operation");
    if (Object.hasOwn(PROPOSAL_OPERATIONS, initialOperation)) field("request_type").value = initialOperation;
    const summary = form.querySelector("[data-proposal-summary]");
    const issueLink = form.querySelector("[data-proposal-issue-link]");
    const urlStatus = form.querySelector("[data-proposal-url-status]");
    const copyStatus = form.querySelector("[data-proposal-copy-status]");
    const validation = form.querySelector("[data-proposal-validation]");
    const touched = new Set();
    let checked = false;
    let errors = {};
    const lookups = [...form.querySelectorAll("[data-lookup]")];
    function fillLookup(box) {
      const query = box.querySelector("[data-lookup-search]").value.toLowerCase().trim();
      const kind = box.dataset.lookupKind === "subject" ? value("subject_kind") : box.dataset.lookupKind;
      const matches = records.filter(record => (kind === "all" || record.kind === kind)
        && `${record.id} ${record.label} ${record.reference}`.toLowerCase().includes(query));
      const select = box.querySelector("[data-lookup-results]");
      select.replaceChildren();
      for (const record of matches) {
        const option = document.createElement("option");
        option.value = String(records.indexOf(record));
        option.textContent = `${record.label} — ${record.reference}`;
        select.append(option);
      }
      select.selectedIndex = -1;
      box.querySelector("[data-lookup-use]").disabled = true;
      box.querySelector("[data-lookup-status]").textContent = matches.length
        ? `${matches.length} matches. Select a record, then use it.` : "No matches in this publication. You can still enter an exact ID from another verified source.";
    }
    const refresh = () => {
      const operation = value("request_type");
      form.querySelector("[data-operation-help]").textContent = PROPOSAL_OPERATIONS[operation];
      const active = [];
      for (const group of groups) {
        const input = group.querySelector("[data-field]");
        group.hidden = !group.dataset.operations.split(" ").includes(operation);
        input.disabled = group.hidden;
        if (!group.hidden) active.push({name: input.dataset.field,
          label: group.querySelector("label").childNodes[0].textContent.trim(),
          help: group.querySelector(".field-help").textContent.trim(),
          value: input.value.trim(), required: input.dataset.required === "true"});
      }
      errors = proposalErrors(active, records);
      for (const group of groups) {
        const input = group.querySelector("[data-field]");
        const error = !group.hidden && (checked || touched.has(input.dataset.field)) ? errors[input.dataset.field] : "";
        group.querySelector("[data-error]").textContent = error || "";
        input.setAttribute("aria-invalid", String(Boolean(error)));
      }
      const markdown = proposalMarkdown(active);
      summary.value = markdown;
      const configured = form.getAttribute(`data-intake-${operation}`);
      const result = proposalURL(configured, form.dataset.provider, active, markdown);
      issueLink.href = Object.keys(errors).length ? configured : result.href;
      issueLink.setAttribute("aria-disabled", String(Boolean(Object.keys(errors).length)));
      urlStatus.textContent = Object.keys(errors).length ? "Complete the required fields and resolve errors before opening your draft."
        : result.overflow ? ("This draft is too long to prefill safely. Copy the full draft below and open the issue form. " + (form.dataset.provider === "gitlab" ? "Paste it into the description, replacing any template answers." : "Copy the title and answers into the matching form fields."))
        : "Your draft is ready. Review the prefilled issue form before submitting.";
      if (form.dataset.provider === "gitlab") urlStatus.textContent += " GitLab 18.1 may append a default template: keep one copy of each answer section.";
      copyStatus.textContent = "";
      if (checked) validation.textContent = Object.keys(errors).length ? `${Object.keys(errors).length} fields need attention. Nothing has been submitted.` : "Draft checked. Nothing has been submitted.";
    };
    for (const box of lookups) {
      fillLookup(box);
      box.querySelector("[data-lookup-search]").addEventListener("input", () => fillLookup(box));
      box.querySelector("[data-lookup-results]").addEventListener("change", () => {
        box.querySelector("[data-lookup-use]").disabled = box.querySelector("[data-lookup-results]").selectedIndex < 0;
      });
      box.querySelector("[data-lookup-use]").addEventListener("click", () => {
        const select = box.querySelector("[data-lookup-results]");
        if (select.selectedIndex < 0) return;
        const record = records[Number(select.value)];
        const name = box.dataset.lookup;
        const input = field(name);
        let addition = record.id;
        if (name === "requested_outcome") addition = `${record.kind}: ${record.reference}`;
        if (name === "candidate_evidence") addition = record.observation;
        if (["subject_identities", "candidate_evidence", "requested_outcome"].includes(name)) {
          const existing = input.value.trim();
          input.value = existing ? existing + "\n" + addition : addition;
        } else input.value = addition;
        touched.add(name); refresh(); input.focus();
      });
    }
    form.addEventListener("input", event => {
      if (!event.target.matches("[data-field]")) return;
      touched.add(event.target.dataset.field); refresh();
    });
    form.addEventListener("change", event => {
      if (!event.target.matches("[data-field]")) return;
      touched.add(event.target.dataset.field);
      if (event.target === field("subject_kind")) for (const box of lookups) fillLookup(box);
      refresh();
    });
    form.addEventListener("submit", event => {
      event.preventDefault(); checked = true; refresh();
      const first = Object.keys(errors)[0]; if (first) field(first).focus();
    });
    issueLink.addEventListener("click", event => {
      checked = true; refresh();
      if (Object.keys(errors).length) { event.preventDefault(); field(Object.keys(errors)[0]).focus(); }
    });
    form.querySelector("[data-copy-summary]").addEventListener("click", async () => {
      try {
        if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
        await navigator.clipboard.writeText(summary.value);
        copyStatus.textContent = "Draft copied. Review it in the issue form before submitting.";
      } catch (_) {
        summary.focus(); summary.select(); copyStatus.textContent = "Select and copy the draft manually.";
      }
    });
    refresh();
    form.hidden = false;
    const anchor = document.getElementById(window.location.hash.slice(1));
    const details = document.getElementById("detailed-proposal");
    if (details && (Object.hasOwn(PROPOSAL_OPERATIONS, initialOperation) || (anchor && details.contains(anchor)))) details.open = true;
    if (anchor && form.contains(anchor)) anchor.scrollIntoView();
  }
}

if (typeof document !== "undefined") {
  const init = () => { initModelRequest(); initProposalBuilder(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
}
