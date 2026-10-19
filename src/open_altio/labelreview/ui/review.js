// The review page: one item at a time or the batch as a list, driven from the keyboard.
// Every element exists from the start and only its text changes, so nothing moves.

const $ = (id) => document.getElementById(id);
let data = null;
let at = 0;
let chosen = null;
let view = "one";
const queue = new URLSearchParams(location.search).get("queue") === "redo" ? "redo" : "phrases";

const redo = () => data.mode === "redo";
const reasonOf = (key) => data.reasons.find((r) => r.key === key);
const pct = (share, digits) => `${(share * 100).toFixed(digits)}%`;
const answerOf = (item) => (redo() ? item.answer : item.decision);
// Section keys such as warnings_and_precautions, as words.
const plain = (s) => (s ? s[0].toUpperCase() + s.slice(1).replaceAll("_", " ") : "");
const termSet = (pts) => new Set((pts || []).map((p) => p.trim().toLowerCase()));
const sameTerms = (a, b) => {
  const x = termSet(a);
  const y = termSet(b);
  return x.size === y.size && [...x].every((t) => y.has(t));
};

function coded(answer) {
  if (!answer) return "";
  if (answer.pts.length) return answer.pts.join("; ");
  const reason = reasonOf(answer.none_reason);
  return reason ? `None: ${reason.name}` : "";
}

function said(item) {
  const s = item.suggestion;
  if (!s) return "";
  if (s.status === "refused") return "Refused";
  if (s.status !== "answered") return "No answer";
  return coded(s);
}

function agrees(item) {
  const d = item.decision;
  const s = item.suggestion;
  if (!d || !s) return null;
  return s.status === "answered" && sameTerms(d.pts, s.pts);
}

async function load() {
  $(queue === "redo" ? "q-redo" : "q-phrases").setAttribute("aria-current", "page");
  const response = await fetch(`/api/state?queue=${queue}`);
  const answer = await response.json();
  if (!response.ok) {
    $("batch-line").textContent = answer.refused ?? "Not available.";
    return;
  }
  data = answer;
  buildReasons();
  render();
}

function buildReasons() {
  data.reasons.forEach((r, i) => {
    const label = document.createElement("label");
    label.dataset.key = r.key;
    label.title = r.name;
    const number = document.createElement("span");
    number.className = "key";
    number.textContent = String(i + 1);
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "reason";
    radio.value = r.key;
    radio.addEventListener("change", () => choose(r.key));
    const name = document.createElement("span");
    name.textContent = r.name;
    label.append(number, radio, name, document.createElement("span"));
    $("reasons").append(label);
  });
  $("d-pts").addEventListener("input", () => {
    if ($("d-pts").value.trim()) choose(null);
  });
}

function choose(key) {
  chosen = key;
  for (const radio of document.querySelectorAll('input[name="reason"]')) radio.checked = radio.value === key;
  if (key) $("d-pts").value = "";
  $("definition").textContent = key ? `${reasonOf(key).name}: ${reasonOf(key).definition}` : "";
}

function render() {
  renderHead();
  renderGates();
  renderItem();
  renderList();
}

function renderHead() {
  $("question").textContent = data.question;
  if (redo()) {
    $("batch-line").textContent =
      `Blind redo, ${data.redo.items} items, ${data.redo.answered} answered, reviewer ${data.reviewer}`;
  } else if (!data.batch) {
    $("batch-line").textContent = "No batch yet. Start one with the batch command.";
  } else {
    $("batch-line").textContent =
      `Batch ${data.batch.number}, ${data.batch.size} items, reviewer ${data.reviewer}`;
  }
}

function setGate(id, text, ok) {
  const el = $(id);
  el.textContent = text;
  el.title = text;
  el.className = ok === null ? "" : ok ? "pass" : "fail";
}

function renderGates() {
  const g = data.gates;
  if (!g) {
    for (const id of ["g-decided", "g-other", "g-agreed", "g-stale", "g-next"]) setGate(id, "", null);
    if (redo()) setGate("g-decided", `${data.redo.answered} of ${data.redo.items}`, null);
    return;
  }
  setGate("g-decided", `${g.decided} of ${g.items}`, g.decided === g.items);
  const otherOk = g.other_share < g.other_share_below;
  setGate("g-other", `${g.other} (${pct(g.other_share, 1)}), under ${pct(g.other_share_below, 0)}`, otherOk);
  const agreeOk = g.agreement >= g.agreement_at_least;
  setGate("g-agreed", `${g.agreed} of ${g.items} (${pct(g.agreement, 0)}), at least ${pct(g.agreement_at_least, 0)}`, agreeOk);
  setGate("g-stale", g.stale === 0 ? "Yes" : `${g.stale} not current`, g.stale === 0);
  const tidy = g.reason_only.length
    ? ` ${g.reason_only.length} differ only in the reason for none, for tidying.`
    : "";
  const next = g.passed
    ? `May start: ${g.next_size} items, with the batch command.${tidy}`
    : `Not yet. ${g.reasons.join(" ")}${tidy}`;
  setGate("g-next", next, g.passed);
}

function sentenceWithEvidence(sentence, evidence) {
  const box = $("f-sentence");
  box.replaceChildren();
  const start = evidence ? sentence.toLowerCase().indexOf(evidence.toLowerCase()) : -1;
  if (start < 0) {
    box.textContent = sentence;
    return;
  }
  const mark = document.createElement("mark");
  mark.textContent = sentence.slice(start, start + evidence.length);
  box.append(sentence.slice(0, start), mark, sentence.slice(start + evidence.length));
}

function renderSuggestion(item) {
  const s = redo() ? null : item.suggestion;
  sentenceWithEvidence(item.sentence, s?.evidence);
  const lines = { answer: "", evidence: "", reason: "", meta: "" };
  if (redo()) lines.answer = "Hidden for the blind redo";
  else if (!s) lines.answer = "No suggestion yet. Run the agent, or export and import.";
  else {
    lines.answer = said(item);
    lines.meta = `${s.by}, instructions version ${s.instructions_version}` +
      (s.current ? "" : ". Not current: run the agent again.");
    if (s.status === "answered") {
      lines.evidence = s.evidence ? `"${s.evidence}"` : "";
      lines.reason = s.note ? `${s.reason} Note: ${s.note}` : s.reason;
    } else {
      lines.reason = s.status === "refused"
        ? "The agent gave no answer, even after every retry. Give the right coding and press Reject."
        : "The agent left this item blank. Give the right coding and press Reject.";
    }
  }
  $("s-answer").textContent = lines.answer;
  $("s-evidence").textContent = lines.evidence;
  $("s-reason").textContent = lines.reason;
  $("s-meta").textContent = lines.meta;
  return s;
}

function renderItem() {
  const item = data.items[at];
  if (!item) {
    $("pos").textContent = "No items";
    return;
  }
  $("pos").textContent = `Item ${at + 1} of ${data.items.length}`;
  $("f-drug").textContent = item.drug;
  $("f-section").textContent = plain(item.section);
  $("f-date").textContent = item.label_date || "Not given";
  $("f-why").textContent = item.why_uncertain;
  $("f-guess").textContent = item.rules_guess || "None";
  const s = renderSuggestion(item);
  const answer = answerOf(item);
  const start = answer ?? (s?.status === "answered" ? s : null);
  choose(start && !start.pts.length ? start.none_reason : null);
  $("d-pts").value = start ? start.pts.join("\n") : "";
  $("d-note").value = answer?.note ?? "";
  $("accept").disabled = redo() || !s || s.status !== "answered";
  $("accept").style.visibility = redo() ? "hidden" : "visible";
  $("reject").firstChild.textContent = redo() ? "Save " : "Reject ";
  const agree = agrees(item);
  const reasonOnly = agree && !answer.pts.length && answer.none_reason !== s.none_reason;
  $("state-word").textContent = !answer
    ? "Not decided"
    : redo()
      ? "Answered"
      : agree
        ? reasonOnly ? "Decided, agrees (another reason for none)" : "Decided, agrees with the agent"
        : "Decided, differs from the agent";
  $("decided-line").textContent = answer
    ? `${redo() ? "Answered" : answer.verdict === "accept" ? "Accepted" : "Rejected"} by ${answer.reviewer}, ${answer.decided_at}`
    : "";
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  td.title = text;
  return td;
}

function renderList() {
  const rows = data.items.map((item, i) => {
    const tr = document.createElement("tr");
    tr.className = i === at ? "at" : "";
    const agree = redo() ? null : agrees(item);
    tr.append(
      cell(String(i + 1)), cell(item.drug), cell(plain(item.section)), cell(item.sentence),
      cell(redo() ? "Hidden" : said(item)), cell(coded(answerOf(item))),
      cell(agree === null ? "" : agree ? "Yes" : "No"),
    );
    tr.addEventListener("click", () => {
      at = i;
      show("one");
    });
    return tr;
  });
  $("rows").replaceChildren(...rows);
}

function show(which) {
  view = which;
  $("one").hidden = which !== "one";
  $("list").hidden = which !== "list";
  $("view-one").setAttribute("aria-selected", String(which === "one"));
  $("view-list").setAttribute("aria-selected", String(which === "list"));
  $("message").textContent = "";
  render();
}

function move(step) {
  const n = data.items.length;
  if (!n) return;
  at = Math.min(n - 1, Math.max(0, at + step));
  $("message").textContent = "";
  render();
}

function nextUndecided() {
  const n = data.items.length;
  for (let k = 1; k <= n; k += 1) {
    const i = (at + k) % n;
    if (!answerOf(data.items[i])) {
      at = i;
      $("message").textContent = "";
      render();
      return;
    }
  }
  $("message").textContent = "Every item is decided.";
}

async function send(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const answer = await response.json();
  if (!response.ok) {
    $("message").textContent = answer.refused ?? answer.detail ?? "Not saved.";
    return;
  }
  data = answer;
  if (at < data.items.length - 1) at += 1;
  render();
  $("message").textContent = "Saved.";
}

function accept() {
  const item = data.items[at];
  if (!item || redo()) return;
  send("/api/decide", { item_id: item.item_id, verdict: "accept", note: $("d-note").value });
}

function reject() {
  const item = data.items[at];
  if (!item) return;
  const pts = $("d-pts").value.split("\n").map((p) => p.trim()).filter(Boolean);
  if (!pts.length && !chosen) {
    $("message").textContent = "Type the preferred terms, or press the number of a reason for none.";
    return;
  }
  const body = { item_id: item.item_id, pts, none_reason: pts.length ? "" : chosen, note: $("d-note").value };
  if (redo()) send("/api/redo", body);
  else send("/api/decide", { ...body, verdict: "reject" });
}

document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey || !data) return;
  if (["INPUT", "TEXTAREA"].includes(event.target.tagName) && event.target.type !== "radio") {
    if (event.key === "Escape") event.target.blur();
    return;
  }
  const key = event.key.toLowerCase();
  const number = Number(event.key);
  if (number >= 1 && number <= data.reasons.length) choose(data.reasons[number - 1].key);
  else if (key === "a") accept();
  else if (key === "r") reject();
  else if (key === "p") $("d-pts").focus();
  else if (key === "n") $("d-note").focus();
  else if (key === "j" || key === "arrowdown" || key === "arrowright") move(1);
  else if (key === "k" || key === "arrowup" || key === "arrowleft") move(-1);
  else if (key === "u") nextUndecided();
  else if (key === "l") show(view === "one" ? "list" : "one");
  else if (key === "enter" && view === "list") show("one");
  else return;
  event.preventDefault();
});

$("accept").addEventListener("click", accept);
$("reject").addEventListener("click", reject);
$("prev").addEventListener("click", () => move(-1));
$("next").addEventListener("click", () => move(1));
$("view-one").addEventListener("click", () => show("one"));
$("view-list").addEventListener("click", () => show("list"));
$("decide").addEventListener("submit", (event) => event.preventDefault());
load();
