// The rule check: a seeded sample of rule-decided flags, each marked right or wrong by hand.
// Every element exists from the start and only its text changes, so nothing moves.

const $ = (id) => document.getElementById(id);
const DAILYMED = "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=";
let data = null;
let at = 0;
let chosen = null;

const pct = (share) => `${(share * 100).toFixed(0)}%`;
const plain = (s) => (s ? s[0].toUpperCase() + s.slice(1).replaceAll("_", " ") : "");
const nameOf = (key) => data.outcomes.find((o) => o.key === key)?.name ?? key;

async function load() {
  const response = await fetch("/api/check");
  const answer = await response.json();
  if (!response.ok) {
    $("line").textContent = answer.refused ?? "Not available.";
    return;
  }
  data = answer;
  buildChoices();
  render();
}

function buildChoices() {
  data.outcomes.forEach((o, i) => {
    const label = document.createElement("label");
    const number = document.createElement("span");
    number.className = "key";
    number.textContent = String(i + 1);
    const radio = document.createElement("input");
    radio.type = "radio";
    radio.name = "outcome";
    radio.value = o.key;
    radio.addEventListener("change", () => choose(o.key));
    const name = document.createElement("span");
    name.textContent = o.name;
    label.append(number, radio, name, document.createElement("span"));
    $("choices").append(label);
  });
}

function choose(key) {
  chosen = key;
  for (const radio of document.querySelectorAll('input[name="outcome"]')) radio.checked = radio.value === key;
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function render() {
  const checked = data.flags.filter((f) => f.check).length;
  $("line").textContent = `${checked} of ${data.flags.length} flags checked, reviewer ${data.reviewer}`;
  $("range-head").textContent = `Likely range (${pct(data.confidence)} confidence)`;
  $("rates").replaceChildren(...data.rates.map((r) => {
    const tr = document.createElement("tr");
    const range = r.checked ? `${pct(r.low)} to ${pct(r.high)}` : "";
    tr.append(cell(r.name), cell(String(r.drawn)), cell(String(r.checked)), cell(String(r.wrong)),
      cell(r.checked ? pct(r.rate) : ""), cell(range));
    return tr;
  }));
  const flag = data.flags[at];
  if (!flag) {
    $("pos").textContent = "No flags in the sample";
    return;
  }
  $("pos").textContent = `Flag ${at + 1} of ${data.flags.length}`;
  $("f-drug").textContent = flag.drug || `RxNorm ${flag.rxcui}`;
  $("f-pt").textContent = flag.pt;
  $("f-outcome").textContent = nameOf(flag.outcome);
  $("f-section").textContent = plain(flag.section) || "Not given";
  $("f-date").textContent = flag.label_date || "Not given";
  const link = $("f-label");
  link.textContent = flag.set_id ? "Open on DailyMed" : "No label";
  if (flag.set_id) link.href = DAILYMED + encodeURIComponent(flag.set_id);
  else link.removeAttribute("href");
  const c = flag.check;
  choose(c && c.verdict === "wrong" ? c.right_outcome : null);
  $("note").value = c?.note ?? "";
  $("state-word").textContent = !c ? "Not checked" : c.verdict === "right" ? "Right" : "Wrong";
  $("decided-line").textContent = c ? `Checked by ${c.reviewer}, ${c.decided_at}` : "";
}

function move(step) {
  at = Math.min(data.flags.length - 1, Math.max(0, at + step));
  $("message").textContent = "";
  render();
}

function nextUnchecked() {
  const n = data.flags.length;
  for (let k = 1; k <= n; k += 1) {
    const i = (at + k) % n;
    if (!data.flags[i].check) {
      at = i;
      $("message").textContent = "";
      render();
      return;
    }
  }
  $("message").textContent = "Every flag in the sample is checked.";
}

async function mark(verdict) {
  const flag = data.flags[at];
  if (!flag) return;
  if (verdict === "wrong" && !chosen) {
    $("message").textContent = "Choose the right outcome first, with a number key.";
    return;
  }
  const response = await fetch("/api/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ flag: flag.flag, verdict, right_outcome: chosen, note: $("note").value }),
  });
  const answer = await response.json();
  if (!response.ok) {
    $("message").textContent = answer.refused ?? answer.detail ?? "Not saved.";
    return;
  }
  data = answer;
  if (at < data.flags.length - 1) at += 1;
  render();
  $("message").textContent = "Saved.";
}

document.addEventListener("keydown", (event) => {
  if (event.metaKey || event.ctrlKey || event.altKey || !data) return;
  if (event.target.tagName === "TEXTAREA") {
    if (event.key === "Escape") event.target.blur();
    return;
  }
  const key = event.key.toLowerCase();
  const number = Number(event.key);
  if (number >= 1 && number <= data.outcomes.length) choose(data.outcomes[number - 1].key);
  else if (key === "y") mark("right");
  else if (key === "w") mark("wrong");
  else if (key === "n") $("note").focus();
  else if (key === "j" || key === "arrowdown" || key === "arrowright") move(1);
  else if (key === "k" || key === "arrowup" || key === "arrowleft") move(-1);
  else if (key === "u") nextUnchecked();
  else return;
  event.preventDefault();
});

$("right").addEventListener("click", () => mark("right"));
$("wrong").addEventListener("click", () => mark("wrong"));
$("prev").addEventListener("click", () => move(-1));
$("next").addEventListener("click", () => move(1));
$("decide").addEventListener("submit", (event) => event.preventDefault());
load();
