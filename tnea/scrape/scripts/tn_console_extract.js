/*
 * TNEA Cutoff Portal — in-browser table scraper (v2, matched to real markup)
 * ----------------------------------------------------------------------------
 * Built from the actual Ant Design (antd) table HTML you provided, so this
 * uses exact selectors instead of guesses:
 *   - rows:        .ant-table-tbody > tr.ant-table-row
 *   - next button: li.ant-pagination-next (disabled via .ant-pagination-disabled
 *                  class / aria-disabled="true" on the <li>, not the <button>)
 *   - page size:   .ant-pagination-options-size-changer
 *   - row identity: data-row-key on each <tr>, e.g. "1-BY-0" -- the trailing
 *                  number is a running index, so watching it change after a
 *                  "next" click is a reliable way to confirm the table has
 *                  actually re-rendered before reading it (this is what fixed
 *                  the page-skipping bug from the previous version).
 *
 * Still only reads the RENDERED table -- never touches the encrypted API.
 *
 * USAGE:
 *   1. On cutoff.tneaonline.org/search, solve the Cloudflare check yourself.
 *   2. Click the tab you want (Cutoff Marks, or Ranks) and set year to 2025.
 *   3. Set the page-size dropdown to "100 / page" if not already.
 *   4. Open DevTools (F12) -> Console.
 *   5. Paste this whole script, press Enter.
 *   6. It will ask you (via a small popup) whether this run is "marks" or
 *      "ranks" -- type that and press OK. This avoids guessing which tab
 *      is active from the page text.
 *   7. Watch progress log in the console. When done, a CSV downloads
 *      automatically.
 *   8. Switch tabs, run again for the other file.
 */

(async function scrapeTneaTable() {
  const CATEGORIES = ["OC", "BC", "BCM", "MBC", "SC", "SCA", "ST"];
  const delay = (ms) => new Promise((res) => setTimeout(res, ms));

  const kind = (window.prompt(
    "Is the currently visible tab 'marks' (Cutoff Marks) or 'ranks' (Ranks)? " +
      "Type exactly: marks OR ranks",
    "marks"
  ) || "marks").trim().toLowerCase();

  const year = (window.prompt("Which year is selected? (e.g. 2025)", "2025") || "2025").trim();

  if (kind !== "marks" && kind !== "ranks") {
    console.error("Didn't recognize that — type exactly 'marks' or 'ranks'. Aborting.");
    return;
  }

  function flattenCell(el) {
    return el.innerText
      .replace(/\s+/g, " ")
      .trim();
  }

  function getRows() {
    return Array.from(document.querySelectorAll(".ant-table-tbody > tr.ant-table-row"));
  }

  function getFirstRowKey() {
    const row = document.querySelector(".ant-table-tbody > tr.ant-table-row");
    return row ? row.getAttribute("data-row-key") : null;
  }

  function readCurrentPageRows() {
    const rows = getRows();
    const out = [];
    for (const row of rows) {
      const cells = Array.from(row.querySelectorAll("td.ant-table-cell"));
      if (cells.length < 3 + CATEGORIES.length) continue;

      const code = cells[0].innerText.trim();
      const college = flattenCell(cells[1]);
      const branch = cells[2].innerText.trim();
      // Strip the trailing "*" (vacant-seat marker) — keep just the number/dash.
      const catValues = CATEGORIES.map((_, i) =>
        cells[3 + i].innerText.trim().replace(/\*+$/, "").trim()
      );

      out.push([code, college, branch, ...catValues]);
    }
    return out;
  }

  function getTotalCount() {
    const totalEl = document.querySelector(".ant-pagination-total-text");
    if (!totalEl) return null;
    const match = totalEl.textContent.match(/of\s+([\d,]+)/);
    return match ? parseInt(match[1].replace(/,/g, ""), 10) : null;
  }

  function getActivePageTitle() {
    const li = document.querySelector("li.ant-pagination-item-active");
    return li ? li.getAttribute("title") : null;
  }

  function getNextButton() {
    const li = document.querySelector("li.ant-pagination-next");
    if (!li) return null;
    const disabled =
      li.classList.contains("ant-pagination-disabled") ||
      li.getAttribute("aria-disabled") === "true";
    if (disabled) return null;
    const btn = li.querySelector("button");
    if (btn && btn.hasAttribute("disabled")) return null;
    return btn;
  }

  async function waitForRowsChange(prevKey, timeoutMs = 10000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const key = getFirstRowKey();
      if (key && key !== prevKey) return key;
      await delay(150);
    }
    return null; // timed out -- caller should treat this as a stall
  }

  function toCsv(rows) {
    const header = ["Code", "College", "Branch", ...CATEGORIES];
    const esc = (v) => {
      const s = String(v ?? "");
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const lines = [header.map(esc).join(",")];
    for (const row of rows) lines.push(row.map(esc).join(","));
    return lines.join("\n");
  }

  function downloadCsv(text, filename) {
    const BOM = "\uFEFF"; // fixes Excel mangling — (em dash) into â€”
    const blob = new Blob([BOM + text], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // ---- main loop ----
  const allRows = [];
  const totalExpected = getTotalCount();
  console.log(`Portal reports ${totalExpected} total rows.`);

  let pageNum = 1;
  let currentKey = getFirstRowKey();
  const MAX_PAGES = 60; // safety cap, well above the ~35 pages expected at 100/page

  while (pageNum <= MAX_PAGES) {
    await delay(200);
    const rows = readCurrentPageRows();
    allRows.push(...rows);

    const activePageTitle = getActivePageTitle();
    console.log(
      `page ${activePageTitle ?? pageNum} -> ${rows.length} rows ` +
        `(total ${allRows.length}${totalExpected ? " / " + totalExpected : ""})`
    );

    if (totalExpected && allRows.length >= totalExpected) {
      console.log("Reached expected total row count -- stopping.");
      break;
    }

    const nextBtn = getNextButton();
    if (!nextBtn) {
      console.log("Next button disabled/missing -- reached last page.");
      break;
    }

    const prevKey = currentKey;
    nextBtn.click();

    const newKey = await waitForRowsChange(prevKey);
    if (!newKey) {
      console.warn(
        "Table did not appear to update within 10s after clicking next. " +
          "Stopping here to avoid capturing duplicate/stale data — " +
          "re-run if this stopped early, or tell me what you see so I can adjust timing."
      );
      break;
    }
    currentKey = newKey;
    pageNum++;
  }

  if (totalExpected && allRows.length !== totalExpected) {
    console.warn(
      `Row count mismatch: collected ${allRows.length}, portal reported ${totalExpected}. ` +
        `Check the log above for where it stopped early before trusting this file.`
    );
  }

  const filename =
    kind === "ranks"
      ? `TN_TNEA_${year}_state_merit_ranks.csv`
      : `TN_TNEA_${year}_cutoff_marks.csv`;

  const csvText = toCsv(allRows);
  downloadCsv(csvText, filename);
  console.log(`Done. ${allRows.length} total rows written to ${filename}`);
})();
