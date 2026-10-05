# Upcoming events dashboard (moved)

**This dashboard has moved.** The upcoming events list now lives in Birdhaus Tools:
https://tools.birdhausmagic.com/upcoming-events/

This repository builds nothing. GitHub Pages serves `docs/`, which holds one static page, `docs/index.html`:
a notice that the page has moved, with a link to the new page. It has no script, no redirect, no loaded asset
and no data, and it needs no other file. The earlier scheduled dashboard was retired on 5 Oct 2026.

## Check (optional)

```bash
python -m unittest discover -s tests
```

`tests/test_moved_notice.py` checks that `docs/` holds only the notice, that its one link is the new page,
and that it carries no script, redirect, loaded asset or event data.
