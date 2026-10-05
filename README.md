# Upcoming events dashboard (moved)

**This dashboard has moved.** The upcoming events list now lives in Birdhaus Tools:
https://tools.birdhausmagic.com/upcoming-events/

This repository no longer builds anything. The scheduled workflow, the Wix data fetcher and the generated
page were removed on 5 Oct 2026 (issue #1), by the owner's ruling. GitHub Pages still serves `docs/`,
which now holds one static notice with a link to the new page: no script, no redirect, no data.

## Check

```bash
python -m unittest discover -s tests
```

`tests/test_moved_notice.py` checks that `docs/` holds only the notice, that its one link is the new
page, and that it carries no script, redirect, loaded asset or event data.
