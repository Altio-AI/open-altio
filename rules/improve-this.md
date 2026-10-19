---
rule: improve-this
values:
  send_to: https://open.altioai.com
enforced_in:
  - src/open_altio/explorer/outbox.py
  - src/open_altio/explorer/ui/outbox.js
  - tests/explorer/test_outbox.py
---
# Improve this sends only the note, and only when asked

Improve this, at the top right of every page, sends a note to Altio's improvements board at `send_to`. It sends only what the dialog says: the words, the page, the part of the page the person pointed at, and an email address if they give one because they want to hear back. With them goes a random id made for that note alone, so a note sent twice is kept once. Nothing else is ever sent: no data, no filters, no counts, no usage, nothing in the background. There is no account and no confirm step.

The page sends the note from the browser, through the same connection and proxy as any page the person opens. Before it goes, it is kept in the copy's outbox, the `outbox` folder in Open Altio's data folder. A note that cannot be sent (offline, or Altio does not answer) waits there and goes the next time a page opens or the browser is back online, and the dialog says so. A note Altio refuses, such as one past its daily cap, is not kept, and the refusal is shown.

**Switching it off:** Settings, Improve this, Hide removes the button in that browser.

**Settings:** `OPEN_ALTIO_IMPROVE_URL` sends notes to another copy of Altio's service, such as one under test, in place of `send_to`. `OPEN_ALTIO_DATA_DIR` moves Open Altio's data folder (by default the platform's own place for an application's data: `~/Library/Application Support/open-altio` on macOS, `%LOCALAPPDATA%\open-altio` on Windows, `~/.local/share/open-altio` elsewhere).

**Why:** a person running their own copy should be able to tell Altio what is confusing, slow or missing as easily as on the hosted service, and should know exactly what leaves their machine when they do.
