# DWG Broker Network — artifact source

Editable source for the published Broker Network directory.

**Live artifact:** https://claude.ai/code/artifact/d629e68c-4d93-4bc1-a2c7-6f3340075ab8

The artifact was originally published as one 1.4MB single-file page. That file is
now split so it can be edited, diffed, and reviewed here.

## Layout

A single working surface built for one job: filter, select, copy, send.

- **Command bar** — search (`/` focuses it), list segments, market filter, live count
- **Table** — sortable on every column, row checkboxes, click any firm name to pull
  everyone at that shop, per-row copy button
- **Action bar** — always states what Copy will put on the clipboard: the selection
  when there is one, otherwise everything in view

Copy is clipboard-only in all four formats including CSV. The artifact sandbox
blocks file downloads, so an Export button would be a dead control.

## Files

```
index.html          page source — layout, styling, all behavior (~900 lines)
brokers.js          6,016 contact records, one per line — window.DWG_BROKERS
assets/logo.png     hero logo (was a 37KB base64 blob inside the HTML)
preview.py          local preview server
```

`index.html` holds page content only. No `<!doctype>`, `<html>`, `<head>` or
`<body>` tags — claude.ai wraps the file in that skeleton at publish time.

## Editing

**Contacts** → `brokers.js`. One JSON record per line:

```
{"n":"Name","c":"Company","e":"email","p":"phone","t":"Title","s":"CA","city":"","src":"source list","cat":"main"}
```

| key | meaning |
| --- | --- |
| `n` `c` `e` `p` `t` | name, company, email, phone, title |
| `s` `city` | state (2-letter), city |
| `src` | origin list, for provenance |
| `cat` | `main` (SLB Brokers), `ohio`, `az` — drives the filter chips and row tag |

Keep the file ASCII: write `—` rather than a literal em dash.

**Layout, filters, copy formats, Ask AI prompt** → `index.html`.

## Preview locally

```bash
python3 preview.py     # http://localhost:8765/.preview.html
```

The **Add Broker** and **Ask AI** panels stay hidden locally. Both need the
claude.ai runtime (`db` and `sample` capabilities) and appear only in the
published artifact.

## Republish

Ask Claude: *"republish broker_network to the live artifact."* The publish call is:

```
Artifact(
  url       = "https://claude.ai/code/artifact/d629e68c-4d93-4bc1-a2c7-6f3340075ab8",
  file_path = "broker_network/index.html",
  root      = "broker_network",
  files     = { "brokers.js": "brokers.js", "assets/logo.png": "assets/logo.png" }
)
```

Same URL, same favicon, same capabilities — omit `favicon` and `capabilities`
on republish and the artifact keeps what it has.

## Two things to know

- **Share pin.** The artifact is shared by link, and viewers stay on the pinned
  version until the pin is moved. Republishing does not push changes to anyone
  holding the link until that happens.
- **Brokers added on the page** are written to the artifact's own database
  (`added_brokers` collection), not to `brokers.js`. They survive republishes.
  To fold them into this repo, pull the collection and append the records.
