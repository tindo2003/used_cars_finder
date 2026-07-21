import { NextRequest, NextResponse } from "next/server";

// First server-side route in this app (everything else is client-side
// Supabase calls) -- needed because Nominatim requires a real
// descriptive User-Agent, which isn't reliably settable from a browser
// fetch. A single on-demand interactive lookup, not a batch job, so no
// caching/persistence like scraper/geocoding.py's in-run cache.
const NOMINATIM_URL = "https://nominatim.openstreetmap.org/search";
const NOMINATIM_USER_AGENT = "used-cars-finder-webapp/1.0";
const ZIP_REGEX = /^\d{5}$/;

export async function GET(request: NextRequest) {
    const zip = request.nextUrl.searchParams.get("zip")?.trim() ?? "";

    if (!ZIP_REGEX.test(zip)) {
        return NextResponse.json({ error: "Enter a 5-digit US zip code." }, { status: 400 });
    }

    try {
        const response = await fetch(
            // ", USA" mirrors scraper/geocoding.py's REGION_SUFFIX trick --
            // disambiguates from other countries' postal codes that share
            // the same 5-digit format.
            `${NOMINATIM_URL}?q=${encodeURIComponent(`${zip}, USA`)}&format=json&limit=1`,
            { headers: { "User-Agent": NOMINATIM_USER_AGENT } }
        );

        if (!response.ok) {
            return NextResponse.json({ error: "Location lookup failed. Try again." }, { status: 502 });
        }

        const results = await response.json();
        const first = results?.[0];
        const lat = first ? parseFloat(first.lat) : NaN;
        const lng = first ? parseFloat(first.lon) : NaN;

        if (!first || Number.isNaN(lat) || Number.isNaN(lng)) {
            return NextResponse.json({ error: `Couldn't find zip code ${zip}.` }, { status: 404 });
        }

        return NextResponse.json({ lat, lng });
    } catch {
        return NextResponse.json({ error: "Location lookup failed. Try again." }, { status: 502 });
    }
}
