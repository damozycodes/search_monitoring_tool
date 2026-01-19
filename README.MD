#

## Overview

The application UI has two tabs on the right: **Search Logs** and **Proxies**. This guide explains how to prepare proxies, configure searches, run the program, and the required Playwright/Python setup.

- **Search Logs** — shows search activity and results.
- **Proxies** — proxy management (scrape, validate, add custom proxies).

---

## Features

- 🌐 **Proxy pipeline**
  - **Scrape** from multiple public sources.
  - **Validate** with a strict timeout and optional country filtering.
  - **Add & persist** custom proxies (e.g., residential).

- ⚙️ **Search execution**
  - **Browser concurrency**: control how many instances run in parallel.
  - **Max searches**: upper limit for a run.
  - **Continuous mode**: auto-refresh proxies on a schedule and resume.
  - **Debug mode**: show actual browser windows (useful for diagnostics; slower & heavier).

- 📊 **Live observability**
  - **Active** workers, **Completed (success)**, **Failed**, **Success rate**, **Remaining**.
  - Detailed **Search Logs** and **Proxy Logs**.
  - Status bar with compact, always-on stats.

---

## Screens & Workflow

### 1) Proxies Tab

1. Go to the **Proxies** tab.
2. Click **Scrape proxies from public sources** to download public proxies. Wait for the scrape to finish.
3. After scraping, click **Check scraped proxies** to validate them.
4. Validation uses the **timeout** you set (the proxy latency/time limit).
5. **Concurrency** determines how many proxies the validator will check in parallel.

**Throughput formula:**  
`throughput (proxies/sec) ≈ concurrency / timeout_seconds`

> Example: If **concurrency = 100** and **timeout = 50s**, then expected throughput ≈ **100 / 50 = 2 proxies/sec** (if each check takes the full timeout). If checks finish faster, throughput increases.

---

### 2) Search Configuration (left panel)

- **Enter keyword to search** — type your search phrase.
- **Browser concurrency** — how many browser instances open simultaneously.  
  _If you set **2**, two browsers will open at the same time and run searches in parallel._
- **Max search** — maximum number of searches the program should perform before stopping.

**Continuous mode (checkbox):**  
When enabled, the program will not permanently stop at the **Max search** limit.  
Example: if continuous mode is enabled and you set a duration of 60 minutes, after 60 minutes (or after the last search you manually started completes), the program will automatically:

- scrape new proxies,
- validate them,
- resume searching using the validated proxies and the last-used keyword (or the keyword present in **Enter keyword to search**).

**Debug (Show browser) mode:**  
When enabled, real browser windows are shown so you can observe behavior.  
**Downsides:** uses substantially more memory and slows down the process compared to headless operation.

---

### 3) Search Logs Tab

- Real-time feed of search activity and outcomes.
- Progress bar reflects **completed (success + failed)**.
- Status shows **Active**, **Completed (success)**, **Failed**, **Success rate**, and **Remaining**.

---

## Performance Tips

- For validation:
  - Increase **Concurrency** to parallelize checks.
  - Tune **Timeout** (seconds) to balance speed vs. reliability.
- For searching:
  - **Headless** (debug off) is faster and lighter.
  - Add **custom (e.g., residential) proxies** for consistency, then validate them.

---

## Install & Run

> **Prerequisites:** Python **3.9+**

1. **Install Playwright Python package:**
   ```bash
   pip install playwright
   ```

2. **Install Playwright browsers (one-time setup per machine):**
   ```bash
   playwright install
   # optionally:
   # playwright install chromium
   ```

3. **Install other dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   ```bash
   python main.py
   ```

> Even if you distribute an executable, Playwright’s browser engines are **not** bundled automatically. The target machine must run `playwright install` once; after that, you can run the executable without additional steps.

---

## Troubleshooting

- **“Playwright not installed / browsers missing.”**  
  Run:
  ```bash
  pip install playwright
  playwright install
  ```

- **“0 working proxies after a check.”**  
  Try a higher timeout (e.g., 10–20s), verify network connectivity, or temporarily disable region filtering to test reachability.

- **“Debug mode is slow.”**  
  Expected: showing real browsers uses more CPU/RAM. Use headless for speed.

- **“Active count doesn’t match concurrency.”**  
  Active reflects the **current** running instances; after a batch completes there might be a brief dip until the scheduler fills new slots.

---

## Quick Start (TL;DR)

1. **Proxies tab** → **Scrape** → **Check** (set **timeout** & **concurrency** first).  
2. Left panel → enter **keyword**, set **Browser concurrency** & **Max search**.  
3. Optionally enable **Continuous mode** or **Debug**.  
4. Run the program and monitor **Search Logs** and status.
