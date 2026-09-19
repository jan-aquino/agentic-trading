const STORAGE_KEY = "simple-value-portfolio-snapshot-v1";
let snapshot;
let selectedSymbol;

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const number = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const percent = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 1, maximumFractionDigits: 1 });

function statusClass(status) {
  return `status-${String(status).toLowerCase().replaceAll("_", "-")}`;
}

function statusLabel(status) {
  return status === "SELL_REVIEW" ? "Sell review" : status === "WATCH" ? "Watch" : "Hold";
}

function safeDate(value) {
  if (!value) return "Not available";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return String(value);
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function safeLink(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch { return "#"; }
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function validateSnapshot(value) {
  if (!value || value.schema_version !== "portfolio-dashboard-v1") throw new Error("This is not a portfolio dashboard snapshot.");
  if (!value.account || !Array.isArray(value.holdings)) throw new Error("The snapshot is missing account or holdings data.");
  for (const holding of value.holdings) {
    if (!holding.symbol || !holding.metrics || !["HOLD", "WATCH", "SELL_REVIEW"].includes(holding.status)) {
      throw new Error(`The ${holding.symbol || "unknown"} holding is incomplete.`);
    }
  }
  return value;
}

async function loadInitialData() {
  const local = localStorage.getItem(STORAGE_KEY);
  if (local) {
    try { return { data: validateSnapshot(JSON.parse(local)), demo: false }; } catch { localStorage.removeItem(STORAGE_KEY); }
  }
  const response = await fetch("sample-snapshot.json");
  if (!response.ok) throw new Error("Could not load the example portfolio.");
  return { data: validateSnapshot(await response.json()), demo: true };
}

function renderSummary() {
  const account = snapshot.account;
  const watchCount = snapshot.holdings.filter(item => item.status !== "HOLD").length;
  document.querySelector("#portfolio-value").textContent = money.format(account.portfolio_equity);
  document.querySelector("#account-label").textContent = account.account_suffix ? `Account ending ${account.account_suffix}` : "Account hidden";
  document.querySelector("#invested-value").textContent = money.format(account.invested_value);
  document.querySelector("#holding-count").textContent = `${snapshot.holdings.length} ${snapshot.holdings.length === 1 ? "holding" : "holdings"}`;
  document.querySelector("#cash-value").textContent = money.format(account.cash_balance);
  document.querySelector("#cash-share").textContent = `${percent.format(account.portfolio_equity ? account.cash_balance / account.portfolio_equity : 0)} of portfolio`;
  const returnNode = document.querySelector("#return-value");
  returnNode.textContent = percent.format(account.unrealized_return);
  returnNode.className = account.unrealized_return >= 0 ? "positive" : "negative";
  document.querySelector("#gain-value").textContent = `${account.unrealized_gain >= 0 ? "+" : ""}${money.format(account.unrealized_gain)}`;
  document.querySelector("#attention-count").textContent = String(watchCount);
  document.querySelector("#attention-copy").textContent = watchCount ? "Open the flagged holdings below" : "Nothing flagged in the latest review";
  document.querySelector("#sidebar-count").textContent = String(snapshot.holdings.length);
  document.querySelector("#updated-label").textContent = `Updated ${safeDate(snapshot.generated_at)}`;
}

function renderHoldingList() {
  const list = document.querySelector("#holding-list");
  list.replaceChildren();
  for (const holding of snapshot.holdings) {
    const button = el("button", "holding-button");
    button.type = "button";
    button.dataset.symbol = holding.symbol;
    button.setAttribute("aria-current", holding.symbol === selectedSymbol ? "true" : "false");
    button.addEventListener("click", () => { selectedSymbol = holding.symbol; render(); });
    const name = el("div", "holding-name");
    name.append(el("strong", "", holding.symbol), el("span", "", holding.company_name));
    const value = el("div", "holding-value");
    value.append(el("div", "", money.format(holding.market_value)));
    const change = el("span", holding.total_return >= 0 ? "positive" : "negative", percent.format(holding.total_return));
    value.append(change);
    button.append(name, value, el("span", `status ${statusClass(holding.status)}`, statusLabel(holding.status)));
    list.append(button);
  }
}

function metricCard(title, metric, formatValue, explanation) {
  const card = el("article", "metric-card");
  card.append(el("p", "", title));
  const values = el("div", "metric-values");
  const then = el("div"); then.append(el("span", "", "When bought"), el("strong", "", formatValue(metric.at_purchase)));
  const now = el("div"); now.append(el("span", "", "Now"), el("strong", "", formatValue(metric.current)));
  values.append(then, el("span", "metric-arrow", "→"), now);
  card.append(values, el("p", "metric-explain", explanation));
  return card;
}

function renderDetail() {
  const holding = snapshot.holdings.find(item => item.symbol === selectedSymbol) || snapshot.holdings[0];
  const panel = document.querySelector("#holding-detail");
  panel.replaceChildren();
  if (!holding) { panel.append(el("div", "empty-state", "No holdings are in this snapshot.")); return; }

  const header = el("div", "detail-header");
  const identity = el("div");
  const symbolRow = el("div", "symbol-row");
  symbolRow.append(el("h2", "", holding.symbol), el("span", `status ${statusClass(holding.status)}`, statusLabel(holding.status)));
  identity.append(symbolRow, el("p", "company-name", `${holding.company_name} · ${number.format(holding.quantity)} shares`));
  const positionValue = el("div", "position-value");
  positionValue.append(el("strong", "", money.format(holding.market_value)), el("span", holding.total_return >= 0 ? "positive" : "negative", `${percent.format(holding.total_return)} since purchase`));
  header.append(identity, positionValue);

  const summary = el("div", "plain-summary");
  summary.append(el("strong", "", "What this means"), el("p", "", holding.status_reason));

  const metricsSection = el("section", "section");
  const metricsHeading = el("div", "section-heading");
  metricsHeading.append(el("h3", "", "The numbers behind the decision"), el("span", "section-note", `Research checked ${safeDate(holding.research_as_of)}`));
  const metrics = el("div", "metric-grid");
  metrics.append(
    metricCard("Earnings per share", holding.metrics.eps_ttm, value => value == null ? "—" : money.format(value), "Higher usually means the company is earning more per share."),
    metricCard("Price-to-earnings ratio", holding.metrics.pe_ttm, value => value == null ? "—" : `${number.format(value)}×`, "Shows how much investors pay for each dollar of annual earnings."),
    metricCard("Average analyst target", holding.metrics.analyst_target, value => value == null ? "—" : money.format(value), "A forecast, not a promise. Use it as supporting context only.")
  );
  metricsSection.append(metricsHeading, metrics);

  const contextSection = el("section", "section content-grid");
  const thesis = el("article", "subpanel");
  thesis.append(el("h3", "", "Why you bought it"), el("p", "", holding.thesis || "No purchase thesis was saved."));
  const earnings = el("div", "earnings-callout", `Next earnings: ${safeDate(holding.next_earnings_date)}. This is the main checkpoint for EPS and guidance.`);
  thesis.append(earnings);
  const watch = el("article", "subpanel");
  watch.append(el("h3", "", "What to watch"));
  const watchList = el("ul", "watch-list");
  for (const item of holding.what_to_watch || []) watchList.append(el("li", "", item));
  watch.append(watchList);
  contextSection.append(thesis, watch);

  const newsSection = el("section", "section");
  const newsHeading = el("div", "section-heading");
  newsHeading.append(el("h3", "", "Recent news"), el("span", "section-note", "Research summaries, not trade instructions"));
  const newsList = el("div", "news-list");
  if (!holding.recent_news?.length) newsList.append(el("div", "no-news", "No recent material news was included in this update."));
  for (const item of holding.recent_news || []) {
    const link = el("a", "news-item");
    link.href = safeLink(item.url); link.target = "_blank"; link.rel = "noopener noreferrer";
    link.append(el("span", `impact-mark impact-${item.impact || "neutral"}`));
    const copy = el("div");
    copy.append(el("strong", "", item.title || "Untitled update"));
    if (item.summary) copy.append(el("p", "", item.summary));
    copy.append(el("span", "", `${item.publisher || "Source"} · ${safeDate(item.published_at)}`));
    link.append(copy); newsList.append(link);
  }
  newsSection.append(newsHeading, newsList);
  panel.append(header, summary, metricsSection, contextSection, newsSection);
}

function render() { renderSummary(); renderHoldingList(); renderDetail(); }

function showToast(message) {
  const toast = document.querySelector("#toast");
  toast.textContent = message; toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 4000);
}

document.querySelector("#snapshot-file").addEventListener("change", async event => {
  const [file] = event.target.files;
  if (!file) return;
  try {
    const imported = validateSnapshot(JSON.parse(await file.text()));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(imported));
    snapshot = imported; selectedSymbol = imported.holdings[0]?.symbol;
    document.querySelector("#demo-notice strong").textContent = "Using your imported snapshot";
    document.querySelector("#demo-notice span").textContent = "The data is stored only in this browser.";
    document.querySelector("#reset-data").hidden = false;
    render(); showToast("Portfolio update imported.");
  } catch (error) { showToast(error.message || "That file could not be imported."); }
  event.target.value = "";
});

document.querySelector("#reset-data").addEventListener("click", () => {
  localStorage.removeItem(STORAGE_KEY); window.location.reload();
});

loadInitialData().then(({ data, demo }) => {
  snapshot = data; selectedSymbol = data.holdings[0]?.symbol;
  if (!demo) {
    document.querySelector("#demo-notice strong").textContent = "Using your imported snapshot";
    document.querySelector("#demo-notice span").textContent = "The data is stored only in this browser.";
    document.querySelector("#reset-data").hidden = false;
  }
  render();
}).catch(error => { document.querySelector("#holding-detail").textContent = error.message; });
