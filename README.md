# Used Car Finder

Finds good used-car deals around the Bay Area. It pulls listings from local dealer sites and Craigslist, flags the ones actually priced below what similar cars are going for (not just the cheapest), and can email you a daily digest of the best matches for what you're looking for.

## What it does

- Search by make, model, year, mileage, and price
- **Good Deal** badge on listings priced meaningfully below comparable cars nearby
- Duplicate listings (the same car posted twice, or synced across a dealer's sister stores) are filtered out automatically
- Save a search and get a daily email digest of the best current matches, best deals first — you'll see the same listing again the next day if it's still a top match, not just the first time it shows up
- Bookmark any listing as a favorite to revisit later
- Listings that haven't shown up in a while quietly drop out, since they're probably already sold

Sign in with an email/password — it's still built for one person, but signing in keeps your saved searches and favorites synced across devices.

## Running it

```bash
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000).

New listings come in automatically every 15 minutes, and the daily email digest goes out each morning — both run on their own in the background, nothing needs to stay open on your end.
