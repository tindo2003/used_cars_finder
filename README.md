# Used Car Finder

Finds good used-car deals around the Bay Area. It pulls listings from local dealer sites and Craigslist, flags the ones actually priced below what similar cars are going for (not just the cheapest), and can email you when something new matches what you're looking for.

## What it does

- Search by make, model, year, mileage, and price
- **Good Deal** badge on listings priced meaningfully below comparable cars nearby
- Duplicate listings (the same car posted twice, or synced across a dealer's sister stores) are filtered out automatically
- Save a search and get a daily email digest when a new match shows up, best deals first
- Listings that haven't shown up in a while quietly drop out, since they're probably already sold

No account needed — it's built for one person.

## Running it

```bash
npm install
npm run dev
```

Then open [http://localhost:3000](http://localhost:3000).

New listings come in automatically every 15 minutes, and the daily email digest goes out each morning — both run on their own in the background, nothing needs to stay open on your end.
