# HBB Flip Scanner

Every weekday after the US close this scans the S&P 500, the Nasdaq-100 and SPY / QQQ / IWM / DIA with the
Hull Bollinger Bands indicator (HMA 34, 2 × stdev 34) and publishes a dashboard page showing:

- **Flipped today**: names whose Hull line turned green or red on today's close, marked *Take* or *Stretched*
  by the 50-day rule (skip a flip if price is already more than 1 ATR past its 50-day average in the flip's direction).
- **Close to flipping**: the exact close that flips each name tomorrow, and how many flat days until it flips.
- **The 25-delta option** for each flip or coming flip: a call for green, a put for red, in the expiry nearest 30 days,
  with IV, skew (25-delta IV minus at-the-money IV), IV minus 20-day realized vol, open interest and spread.

Data is free: prices and option chains from Yahoo Finance (through the `yfinance` package), index members from Wikipedia.
The indicator math matches the TradingView script bar-for-bar.

## Set up (about 10 minutes, once)

1. **Create a repository.** On github.com click **New repository**, name it `hbb-scanner`, choose **Public**
   (free GitHub Pages needs a public repo), leave every box unticked and click **Create repository**.
2. **Upload the files.** On the new repo's page click **uploading an existing file**. Unzip `hbb-scanner.zip`
   on your computer, open the folder, select everything inside it (including the `.github` folder) and drag it
   onto the page. Click **Commit changes**.
   Check that a `.github` folder now shows in the repo. If it doesn't (some browsers skip folders starting
   with a dot): **Add file → Create new file**, type the name `.github/workflows/daily-scan.yml`, paste the
   contents of that file from the zip, and click **Commit changes**.
3. **Allow the scan to save its results.** **Settings → Actions → General → Workflow permissions →
   Read and write permissions → Save.**
4. **Run the first scan.** **Actions** tab → if asked, click **I understand my workflows, go ahead and enable them** →
   **HBB daily scan** → **Run workflow**. It takes 5–15 minutes.
5. **Publish the dashboard.** **Settings → Pages → Build and deployment → Source: Deploy from a branch →
   Branch: `main`, folder `/docs` → Save.** After a minute the page is live at
   `https://<your-github-name>.github.io/hbb-scanner/`.

After that it runs on its own Monday–Friday at 22:20 UTC (4:20 pm Central in winter, 5:20 pm in summer).
Click **Run workflow** any time for an extra scan.

## Run it on your own computer instead (optional)

```
pip install -r requirements.txt
python scan.py           # real data, writes docs/index.html
python scan.py --demo    # offline sample data, to check the page
```

Open `docs/index.html` in a browser.

## Settings

In `scanner/hbb.py`: `HMA_LEN`, `BB_LEN`, `BB_MULT`, `MA_LEN` (50), `MAX_STRETCH` (1.0 ATR).
In `scan.py`: `NEAR_DAYS` (3) and `MAX_OPTION_PULLS` (160).
In `scanner/options.py`: `TARGET_DAYS` (30) and `MIN_DAYS` (20) for the option expiry.

## Good to know

- **IV rank** shows *building* until the scanner has about 60 days of its own history. Each run saves the
  option vols it pulls to `data/iv_history.csv`.
- **Option chains** are pulled only for today's flips, names within 3 flat days of flipping, and the four
  index ETFs, which keeps the free API polite.
- **Yahoo sometimes rate-limits** cloud servers. If a run shows *no chain* for many names, run it again later.
- **Delta** is computed with Black-Scholes from each contract's own implied vol, with no dividend yield.
- **Past results:** every day's full scan is saved in `docs/data/scans/`.
- **Research tool, not trading advice.** The 50-day rule came from a grains study and hasn't been tested on stocks.
