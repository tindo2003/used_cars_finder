"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { createClient } from "@/utils/supabase/client";
import Image from "next/image";

const YEAR_MIN = 1990;
const YEAR_MAX = new Date().getFullYear();
const MILEAGE_MAX = 200000;
const PRICE_MAX = 100000;
const PAGE_SIZE = 50;

// Dealer feeds store transmission as a highly specific, manufacturer-
// worded string (e.g. "6-Speed Automatic ECT-i", "9-Speed 948TE
// Automatic") rather than a clean Automatic/Manual split -- a customer
// picking the literal "Automatic" option would miss almost all of them.
// This sentinel value (never a real transmission string) offers one
// quick "any of the automatic variants" bucket via a substring match,
// without needing to enumerate every manufacturer-specific spelling.
//
// Deliberately literal, not semantic: only matches values containing
// the word "automatic". CVT ("CVT Lineartronic", "eCVT", ...) and
// dual-clutch transmissions ("PDK", "DCT", "DSG"-without-"Automatic")
// are functionally no-clutch-pedal/automatic-like too, but a user call
// (2026-07-20) was to keep this bucket strictly literal rather than
// broadening it to cover them -- a shopper wanting a CVT/dual-clutch
// car picks its exact raw value instead.
const ANY_AUTOMATIC_VALUE = "__any_automatic__";
const isAutomaticTransmission = (value: string) => value.toLowerCase().includes("automatic");

const inputTextClass = "text-slate-900 placeholder:text-slate-400";

// marketplace_source is an internal platform code (e.g. "dealerinspire",
// "dealeron"), not something a customer would recognize. Prefer the
// actual dealership name (with city) when we have it; only fall back to
// a friendly marketplace label for non-dealer sources like Craigslist.
const MARKETPLACE_LABELS: Record<string, string> = {
    craigslist: "Craigslist",
    ebay: "eBay",
};

function getSellerLabel(car: any) {
    if (car.dealer_name) {
        return car.city ? `${car.dealer_name} · ${car.city}` : car.dealer_name;
    }
    return MARKETPLACE_LABELS[car.marketplace_source] ?? car.marketplace_source;
}

// last_seen_at is stamped by the scraper every time it re-confirms a
// listing is still up (see scraper/db.py) -- surfacing it as "Updated
// X ago" tells the customer how fresh/likely-still-available a listing
// is, without needing to explain the underlying mechanism.
//
// Second-level granularity (unlike the old minutes-only version) so the
// monitoring widget's "last crawl" stat can read like a live tick
// ("18 seconds ago") rather than jumping straight to "just now".
function formatRelativeTime(value: unknown): string | null {
    if (typeof value !== "string") return null;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return null;

    const diffSeconds = Math.round((Date.now() - date.getTime()) / 1000);
    if (diffSeconds < 10) return "just now";
    if (diffSeconds < 60) return `${diffSeconds} seconds ago`;

    const diffMinutes = Math.round(diffSeconds / 60);
    if (diffMinutes < 60) return `${diffMinutes} minute${diffMinutes === 1 ? "" : "s"} ago`;

    const diffHours = Math.round(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;

    const diffDays = Math.round(diffHours / 24);
    return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
}

function formatLastSeen(lastSeenAt: unknown): string | null {
    const relative = formatRelativeTime(lastSeenAt);
    return relative ? `Updated ${relative}` : null;
}

// deal_score/is_good_deal are computed server-side (scraper/deals.py,
// refreshed daily) and stored on the row -- the heuristic lives in one
// place (Python), the frontend just sorts/displays the stored value.
const SORT_OPTIONS = [
    { value: "best_deal", label: "Best Deal", column: "deal_score", ascending: false },
    { value: "newest", label: "Newest Listings", column: "posted_at", ascending: false },
    { value: "price_asc", label: "Lowest Price", column: "price", ascending: true },
    { value: "price_desc", label: "Highest Price", column: "price", ascending: false },
    { value: "mileage_asc", label: "Lowest Mileage", column: "mileage", ascending: true },
] as const;

// Dealer feeds aren't consistent about casing (e.g. "Toyota" vs
// "TOYOTA" both appear in production) -- collapse those into one
// option, keeping the first-seen casing as the display value.
function dedupeCaseInsensitive(values: string[]): string[] {
    const seen = new Map<string, string>();
    for (const value of values) {
        const key = value.toLowerCase();
        if (!seen.has(key)) seen.set(key, value);
    }
    return Array.from(seen.values()).sort();
}

function describeSavedSearch(search: any) {
    const parts = [];
    if (search.make?.length) parts.push(search.make.join(", "));
    if (search.model?.length) parts.push(search.model.join(", "));
    const vehicle = parts.length > 0 ? parts.join(" ") : "Any vehicle";

    const filters = [];
    if (search.min_year) filters.push(`${search.min_year}+`);
    if (search.max_mileage) filters.push(`under ${search.max_mileage.toLocaleString()} mi`);
    if (search.max_price) filters.push(`under $${search.max_price.toLocaleString()}`);
    if (search.transmission) filters.push(search.transmission === ANY_AUTOMATIC_VALUE ? "Any Automatic" : search.transmission);
    if (search.seller_type) filters.push(search.seller_type);

    const description = filters.length > 0 ? `${vehicle} — ${filters.join(", ")}` : vehicle;
    const grouping =
        search.notification_grouping && search.notification_grouping !== "combined"
            ? ` (grouped by ${search.notification_grouping})`
            : "";

    return description + grouping;
}

// A minimal checkbox multi-select: no autocomplete, options are just
// whatever distinct values are already in `listings` (see
// fetchFilterOptions). Labelable via `<label htmlFor>` so
// getByLabelText finds the toggle button in tests, same as a plain
// input would.
function MultiSelectDropdown({
    id,
    label,
    options,
    selected,
    onChange,
}: {
    id: string;
    label: string;
    options: string[];
    selected: string[];
    onChange: (next: string[]) => void;
}) {
    const [open, setOpen] = useState(false);
    const [query, setQuery] = useState("");

    const toggleValue = (value: string) => {
        onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
    };

    const summary = selected.length === 0 ? `All ${label}s` : selected.join(", ");
    const filteredOptions = query.trim()
        ? options.filter((option) => option.toLowerCase().includes(query.trim().toLowerCase()))
        : options;

    return (
        <div className="relative">
            <label
                htmlFor={id}
                className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
            >
                {label}
            </label>
            <button
                id={id}
                type="button"
                onClick={() => setOpen((prev) => !prev)}
                aria-expanded={open}
                className={`w-full text-left border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition truncate ${inputTextClass}`}
            >
                {summary}
            </button>
            {open && (
                <div className="absolute z-20 mt-1 w-full max-h-72 overflow-y-auto bg-white border border-slate-300 rounded-lg shadow-lg p-2 space-y-1">
                    <div className="sticky top-0 bg-white flex items-center gap-2 mb-1">
                        <input
                            type="text"
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            placeholder={`Search ${label.toLowerCase()}s...`}
                            aria-label={`Search ${label}`}
                            className={`flex-1 border border-slate-200 rounded p-2 text-sm ${inputTextClass}`}
                        />
                        <button
                            type="button"
                            onClick={() => setOpen(false)}
                            aria-label={`Close ${label}`}
                            className="shrink-0 w-8 h-8 flex items-center justify-center rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
                        >
                            ✕
                        </button>
                    </div>
                    {filteredOptions.length === 0 && (
                        <p className="text-sm text-slate-400 px-2 py-1">No matches</p>
                    )}
                    {filteredOptions.map((option) => (
                        <label
                            key={option}
                            className="flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-50 cursor-pointer text-sm text-slate-800"
                        >
                            <input
                                type="checkbox"
                                checked={selected.includes(option)}
                                onChange={() => toggleValue(option)}
                            />
                            {option}
                        </label>
                    ))}
                </div>
            )}
        </div>
    );
}

// A "just for fun" live status widget. activeListings/newToday/lastCrawl
// are each a cheap aggregate query (exact count or order+limit(1)) -- no
// row data crosses the wire for those. sourceCount is the one stat
// PostgREST can't compute as an aggregate (no SELECT DISTINCT), so it's
// the only query that paginates through matching rows, and only fetches
// the 2 columns it actually needs (see fetchDistinctSourceCount) rather
// than pulling every active listing's full row on every 30s poll like
// this used to.
function MonitoringStats({ supabase }: { supabase: ReturnType<typeof createClient> }) {
    const [stats, setStats] = useState<{
        sourceCount: number;
        activeListings: number;
        newToday: number;
        lastCrawl: string | null;
    } | null>(null);
    const [, setTick] = useState(0);

    const fetchDistinctSourceCount = useCallback(async () => {
        // PostgREST caps a single response at its default max-rows (1000),
        // so this still needs to paginate to see every source -- but only
        // 2 skinny columns per row, not the full stats row shape.
        const pageSize = 1000;
        const sourceSet = new Set<string>();
        let from = 0;
        while (true) {
            const { data, error } = await supabase
                .from("listings")
                .select("dealer_name, marketplace_source")
                .eq("status", "active")
                .is("duplicate_of", null)
                .order("id", { ascending: true })
                .range(from, from + pageSize - 1);

            if (error || !data) break;
            for (const row of data as any[]) {
                const source = row.dealer_name || row.marketplace_source;
                if (source) sourceSet.add(source);
            }
            if (data.length < pageSize) break;
            from += pageSize;
        }
        return sourceSet.size;
    }, [supabase]);

    const fetchStats = useCallback(async () => {
        const startOfToday = new Date();
        startOfToday.setHours(0, 0, 0, 0);

        const activeFilter = () =>
            supabase.from("listings").select("id", { count: "exact", head: true }).eq("status", "active").is("duplicate_of", null);

        const [activeResult, newTodayResult, lastCrawlResult, sourceCount] = await Promise.all([
            activeFilter(),
            activeFilter().gte("created_at", startOfToday.toISOString()),
            supabase
                .from("listings")
                .select("last_seen_at")
                .eq("status", "active")
                .is("duplicate_of", null)
                .order("last_seen_at", { ascending: false, nullsFirst: false })
                .limit(1),
            fetchDistinctSourceCount(),
        ]);

        if (!activeResult.error && !newTodayResult.error && !lastCrawlResult.error) {
            setStats({
                sourceCount,
                activeListings: activeResult.count ?? 0,
                newToday: newTodayResult.count ?? 0,
                lastCrawl: lastCrawlResult.data?.[0]?.last_seen_at ?? null,
            });
        }
    }, [supabase, fetchDistinctSourceCount]);

    useEffect(() => {
        fetchStats();
        const poll = setInterval(fetchStats, 30000);
        return () => clearInterval(poll);
    }, [fetchStats]);

    useEffect(() => {
        const tick = setInterval(() => setTick((t) => t + 1), 1000);
        return () => clearInterval(tick);
    }, []);

    if (!stats || stats.activeListings === 0) return null;

    return (
        <section className="bg-slate-900 text-white p-5 rounded-2xl shadow-sm">
            <p className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                Currently monitoring
            </p>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div>
                    <p className="text-2xl font-extrabold">{stats.sourceCount}</p>
                    <p className="text-xs text-slate-400">source{stats.sourceCount === 1 ? "" : "s"}</p>
                </div>
                <div>
                    <p className="text-2xl font-extrabold">{stats.activeListings.toLocaleString()}</p>
                    <p className="text-xs text-slate-400">active listings</p>
                </div>
                <div>
                    <p className="text-2xl font-extrabold">{stats.newToday.toLocaleString()}</p>
                    <p className="text-xs text-slate-400">new today</p>
                </div>
                <div>
                    <p className="text-2xl font-extrabold">{formatRelativeTime(stats.lastCrawl) ?? "—"}</p>
                    <p className="text-xs text-slate-400">last crawl</p>
                </div>
            </div>
        </section>
    );
}

export default function Home() {
    const supabase = createClient();

    // --- Filter State ---
    const [make, setMake] = useState<string[]>([]);
    const [model, setModel] = useState<string[]>([]);
    const [filterOptionRows, setFilterOptionRows] = useState<
        { make: string; model: string; transmission: string | null; seller_type: string | null }[]
    >([]);
    const [transmission, setTransmission] = useState("");
    const [sellerType, setSellerType] = useState("");
    const [minYear, setMinYear] = useState(YEAR_MIN);
    const [maxMileage, setMaxMileage] = useState(MILEAGE_MAX);
    const [maxPrice, setMaxPrice] = useState(PRICE_MAX);
    const [sortBy, setSortBy] = useState<(typeof SORT_OPTIONS)[number]["value"]>("best_deal");

    // --- Data State ---
    const [listings, setListings] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [loadingMore, setLoadingMore] = useState(false);
    const [hasMore, setHasMore] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // --- Save Search State ---
    const [searchName, setSearchName] = useState("");
    const [email, setEmail] = useState("");
    const [saveStatus, setSaveStatus] = useState<
        "idle" | "loading" | "success" | "error"
    >("idle");
    const [notificationGrouping, setNotificationGrouping] = useState<"combined" | "make" | "model">("combined");
    const [mySavedSearches, setMySavedSearches] = useState<any[]>([]);
    const [savedSearchesExpanded, setSavedSearchesExpanded] = useState(true);
    const [editingSearchId, setEditingSearchId] = useState<string | null>(null);

    // --- Favorites State ---
    const [favoriteListingIds, setFavoriteListingIds] = useState<Set<string>>(new Set());
    const [myFavorites, setMyFavorites] = useState<any[]>([]);
    const [favoritesExpanded, setFavoritesExpanded] = useState(true);

    // --- Auth State ---
    const [user, setUser] = useState<any>(null);
    const [authMode, setAuthMode] = useState<"signIn" | "signUp">("signIn");
    const [authEmail, setAuthEmail] = useState("");
    const [authPassword, setAuthPassword] = useState("");
    const [authError, setAuthError] = useState<string | null>(null);
    const [authSubmitting, setAuthSubmitting] = useState(false);

    useEffect(() => {
        supabase.auth.getUser().then(({ data }) => {
            setUser(data.user ?? null);
        });

        const {
            data: { subscription },
        } = supabase.auth.onAuthStateChange((_event, session) => {
            setUser(session?.user ?? null);
        });

        return () => subscription.unsubscribe();
    }, [supabase]);

    // Prefills the digest-recipient email from the logged-in account once
    // available, without clobbering anything the customer already typed.
    useEffect(() => {
        if (user?.email) {
            setEmail((prev) => prev || user.email);
        }
    }, [user]);

    // --- Core Logic ---
    // Shared by the initial fetch and "Load More" -- both just apply a
    // different .range() on top of the same filtered/sorted query.
    const buildListingsQuery = useCallback(() => {
        const sortOption = SORT_OPTIONS.find((option) => option.value === sortBy) ?? SORT_OPTIONS[0];

        // last_seen_at is a tiebreaker only, not a sort option of its
        // own: when the primary sort has ties (e.g. two listings at
        // the same price), the one the scraper most recently
        // reconfirmed is more likely still available (see
        // scraper/staleness.py) and is preferred. `id` is a final
        // tiebreaker so ordering (and therefore pagination via
        // .range()) is fully deterministic even when both of the above
        // tie too.
        let query = supabase
            .from("listings")
            .select("*")
            .eq("status", "active")
            .is("duplicate_of", null)
            .order(sortOption.column, { ascending: sortOption.ascending, nullsFirst: false })
            .order("last_seen_at", { ascending: false, nullsFirst: false })
            .order("id", { ascending: true });

        // ilike with no wildcards is a case-insensitive exact match --
        // used instead of .in() because dealer feeds aren't
        // consistent about make/model casing (e.g. "Toyota" vs
        // "TOYOTA" both appear in production).
        if (make.length > 0) query = query.or(make.map((m) => `make.ilike.${m}`).join(","));
        if (model.length > 0) query = query.or(model.map((m) => `model.ilike.${m}`).join(","));
        if (transmission === ANY_AUTOMATIC_VALUE) query = query.ilike("transmission", "%automatic%");
        else if (transmission) query = query.ilike("transmission", transmission);
        if (sellerType) query = query.ilike("seller_type", sellerType);
        if (minYear > YEAR_MIN) query = query.gte("model_year", minYear);
        if (maxMileage < MILEAGE_MAX) query = query.lte("mileage", maxMileage);
        if (maxPrice < PRICE_MAX) query = query.lte("price", maxPrice);

        return query;
    }, [make, model, transmission, sellerType, minYear, maxMileage, maxPrice, sortBy, supabase]);

    const fetchListings = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const { data, error: fetchError } = await buildListingsQuery().range(0, PAGE_SIZE - 1);

            if (fetchError) throw fetchError;
            setListings(data || []);
            // If a full page came back, there's likely more -- avoids a
            // separate count query, at the cost of one extra "Load More"
            // click when the result count lands exactly on a page
            // boundary.
            setHasMore((data || []).length === PAGE_SIZE);
        } catch (err: any) {
            setError(err.message || "Failed to fetch listings.");
        } finally {
            setLoading(false);
        }
    }, [buildListingsQuery]);

    useEffect(() => {
        fetchListings();
    }, [fetchListings]);

    const handleLoadMore = async () => {
        setLoadingMore(true);
        try {
            const { data, error: fetchError } = await buildListingsQuery().range(
                listings.length,
                listings.length + PAGE_SIZE - 1
            );

            if (fetchError) throw fetchError;
            setListings((prev) => [...prev, ...(data || [])]);
            setHasMore((data || []).length === PAGE_SIZE);
        } catch (err: any) {
            setError(err.message || "Failed to load more listings.");
        } finally {
            setLoadingMore(false);
        }
    };

    // Populates the make/model multi-select options from whatever
    // distinct values are actually in the inventory right now -- no
    // autocomplete, no static list to keep in sync with real data.
    // Dealer feeds aren't consistent about casing (e.g. "Toyota" vs
    // "TOYOTA" both appear in production), so options are deduped
    // case-insensitively -- otherwise the same brand would show up as
    // several confusing near-duplicate checkboxes.
    const fetchFilterOptions = useCallback(async () => {
        const { data, error: fetchError } = await supabase
            .from("listings")
            .select("make, model, transmission, seller_type")
            .eq("status", "active");

        if (!fetchError && data) {
            setFilterOptionRows(
                (data as any[])
                    .filter((row) => row.make && row.model)
                    .map((row) => ({
                        make: row.make as string,
                        model: row.model as string,
                        transmission: (row.transmission as string) || null,
                        seller_type: (row.seller_type as string) || null,
                    }))
            );
        }
    }, [supabase]);

    useEffect(() => {
        fetchFilterOptions();
    }, [fetchFilterOptions]);

    const availableMakes = useMemo(
        () => dedupeCaseInsensitive(filterOptionRows.map((row) => row.make)),
        [filterOptionRows]
    );

    // Only offer models that actually belong to one of the selected
    // makes -- picking "Toyota" shouldn't leave "Civic" in the list.
    // No makes selected means no narrowing (every model is an option).
    const availableModels = useMemo(() => {
        const selectedMakes = new Set(make.map((m) => m.toLowerCase()));
        const relevantRows =
            selectedMakes.size > 0
                ? filterOptionRows.filter((row) => selectedMakes.has(row.make.toLowerCase()))
                : filterOptionRows;
        return dedupeCaseInsensitive(relevantRows.map((row) => row.model));
    }, [filterOptionRows, make]);

    // If narrowing (or changing) the make selection drops a previously
    // selected model out of the now-relevant list, drop it from the
    // filter too rather than leaving an invisible, no-longer-explained
    // filter silently narrowing results.
    useEffect(() => {
        setModel((prev) => {
            const stillAvailable = new Set(availableModels.map((m) => m.toLowerCase()));
            const next = prev.filter((m) => stillAvailable.has(m.toLowerCase()));
            return next.length === prev.length ? prev : next;
        });
    }, [availableModels]);

    // Transmission narrows to whatever's actually available for the
    // selected make(s) AND model(s) -- picking "Toyota Camry" shouldn't
    // leave a transmission in the list that no Camry in inventory has.
    const availableTransmissions = useMemo(() => {
        const selectedMakes = new Set(make.map((m) => m.toLowerCase()));
        const selectedModels = new Set(model.map((m) => m.toLowerCase()));
        const relevantRows = filterOptionRows.filter(
            (row) =>
                (selectedMakes.size === 0 || selectedMakes.has(row.make.toLowerCase())) &&
                (selectedModels.size === 0 || selectedModels.has(row.model.toLowerCase()))
        );
        return dedupeCaseInsensitive(
            relevantRows.map((row) => row.transmission).filter((t): t is string => Boolean(t))
        );
    }, [filterOptionRows, make, model]);

    // If narrowing make/model drops the selected transmission out of the
    // now-relevant list, clear it too, same reasoning as the model prune.
    // "Any Automatic" stays valid as long as some automatic variant is
    // still available, since it isn't itself one of the raw values.
    useEffect(() => {
        if (!transmission) return;
        const stillValid =
            transmission === ANY_AUTOMATIC_VALUE
                ? availableTransmissions.some(isAutomaticTransmission)
                : availableTransmissions.some((t) => t.toLowerCase() === transmission.toLowerCase());
        if (!stillValid) setTransmission("");
    }, [availableTransmissions, transmission]);

    // seller_type is only ever "dealer" or unset in practice today
    // (Craigslist/eBay don't expose an owner/dealer distinction at list
    // level) -- built from real distinct values rather than a hardcoded
    // guess so this never offers an option that can't match. Not
    // narrowed by make/model (unlike transmission above) since it wasn't
    // asked for and dealer-vs-private isn't a per-vehicle-model thing.
    const availableSellerTypes = useMemo(
        () =>
            dedupeCaseInsensitive(
                filterOptionRows.map((row) => row.seller_type).filter((s): s is string => Boolean(s))
            ),
        [filterOptionRows]
    );

    const fetchMySavedSearches = useCallback(async () => {
        if (!user) {
            setMySavedSearches([]);
            return;
        }
        const { data, error: fetchError } = await supabase
            .from("saved_searches")
            .select("*")
            .eq("user_id", user.id);
        if (!fetchError) {
            setMySavedSearches(data || []);
        }
    }, [supabase, user]);

    useEffect(() => {
        fetchMySavedSearches();
    }, [fetchMySavedSearches]);

    const fetchMyFavorites = useCallback(async () => {
        if (!user) {
            setMyFavorites([]);
            setFavoriteListingIds(new Set());
            return;
        }
        const { data, error: fetchError } = await supabase
            .from("favorites")
            .select("*, listings(*)")
            .eq("user_id", user.id);
        if (!fetchError) {
            const favoritedListings = (data || []).map((row: any) => row.listings).filter(Boolean);
            setMyFavorites(favoritedListings);
            setFavoriteListingIds(new Set(favoritedListings.map((listing: any) => listing.id)));
        }
    }, [supabase, user]);

    useEffect(() => {
        fetchMyFavorites();
    }, [fetchMyFavorites]);

    // --- Handlers ---
    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        fetchListings();
    };

    const handleClearFilters = () => {
        setMake([]);
        setModel([]);
        setTransmission("");
        setSellerType("");
        setMinYear(YEAR_MIN);
        setMaxMileage(MILEAGE_MAX);
        setMaxPrice(PRICE_MAX);
    };

    const handleSaveSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!user) {
            alert("Please log in first to save a search.");
            return;
        }
        if (!email) {
            alert("Please enter an email address first.");
            return;
        }

        const hasNoFilters =
            make.length === 0 &&
            model.length === 0 &&
            !transmission &&
            !sellerType &&
            minYear === YEAR_MIN &&
            maxMileage === MILEAGE_MAX &&
            maxPrice === PRICE_MAX;

        if (hasNoFilters) {
            const proceed = window.confirm(
                "You haven't set any filters, so this search won't be very targeted. " +
                    "We'll still email you the 10 lowest-priced listings overall instead of every listing. Save anyway?"
            );
            if (!proceed) return;
        }

        setSaveStatus("loading");

        const payload = {
            name: searchName.trim() || null,
            email: email.trim(),
            make: make.length > 0 ? make : null,
            model: model.length > 0 ? model : null,
            transmission: transmission || null,
            seller_type: sellerType || null,
            min_year: minYear > YEAR_MIN ? minYear : null,
            max_mileage: maxMileage < MILEAGE_MAX ? maxMileage : null,
            max_price: maxPrice < PRICE_MAX ? maxPrice : null,
            notification_grouping: notificationGrouping,
        };

        const { data, error } = editingSearchId
            ? await supabase.from("saved_searches").update(payload).eq("id", editingSearchId).select().single()
            : await supabase
                  .from("saved_searches")
                  .insert({ ...payload, user_id: user.id })
                  .select()
                  .single();

        if (error) {
            console.error("Supabase Save Error:", error);
            setSaveStatus("error");
            setTimeout(() => setSaveStatus("idle"), 3000);
        } else {
            setSaveStatus("success");
            if (data?.id) {
                setMySavedSearches((prev) =>
                    editingSearchId ? prev.map((search) => (search.id === data.id ? data : search)) : [...prev, data]
                );
            }
            // Keep showing "Updated!"/editing state for the same 3s
            // window as the success color, then reset -- clearing
            // editingSearchId immediately would flip the button back to
            // "Saved!" before the customer ever saw "Updated!".
            setTimeout(() => {
                setSaveStatus("idle");
                if (editingSearchId) handleCancelEdit();
                else setSearchName("");
            }, 3000);
        }
    };

    const handleEditSavedSearch = (search: any) => {
        setEditingSearchId(search.id);
        setSearchName(search.name || "");
        setEmail(search.email || "");
        setMake(search.make || []);
        setModel(search.model || []);
        setTransmission(search.transmission || "");
        setSellerType(search.seller_type || "");
        setMinYear(search.min_year || YEAR_MIN);
        setMaxMileage(search.max_mileage || MILEAGE_MAX);
        setMaxPrice(search.max_price || PRICE_MAX);
        setNotificationGrouping(search.notification_grouping || "combined");
        window.scrollTo({ top: 0, behavior: "smooth" });
    };

    const handleCancelEdit = () => {
        setEditingSearchId(null);
        setSearchName("");
        handleClearFilters();
        setNotificationGrouping("combined");
    };

    const handleDeleteSavedSearch = async (id: string) => {
        const { error } = await supabase.from("saved_searches").delete().eq("id", id);
        if (error) {
            console.error("Supabase Delete Error:", error);
            return;
        }
        setMySavedSearches((prev) => prev.filter((search) => search.id !== id));
        if (editingSearchId === id) handleCancelEdit();
    };

    const handleToggleSavedSearchActive = async (search: any) => {
        const nextActive = !(search.is_active ?? true);
        const { error } = await supabase
            .from("saved_searches")
            .update({ is_active: nextActive })
            .eq("id", search.id);
        if (error) {
            console.error("Supabase Update Error:", error);
            return;
        }
        setMySavedSearches((prev) =>
            prev.map((s) => (s.id === search.id ? { ...s, is_active: nextActive } : s))
        );
    };

    const handleToggleFavorite = async (car: any) => {
        if (!user) return;

        const isFavorited = favoriteListingIds.has(car.id);
        if (isFavorited) {
            const { error } = await supabase
                .from("favorites")
                .delete()
                .eq("user_id", user.id)
                .eq("listing_id", car.id);
            if (error) {
                console.error("Supabase Delete Error:", error);
                return;
            }
            setFavoriteListingIds((prev) => {
                const next = new Set(prev);
                next.delete(car.id);
                return next;
            });
            setMyFavorites((prev) => prev.filter((listing) => listing.id !== car.id));
        } else {
            const { error } = await supabase
                .from("favorites")
                .insert({ user_id: user.id, listing_id: car.id });
            if (error) {
                console.error("Supabase Insert Error:", error);
                return;
            }
            setFavoriteListingIds((prev) => new Set(prev).add(car.id));
            setMyFavorites((prev) => [...prev, car]);
        }
    };

    const handleAuthSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setAuthSubmitting(true);
        setAuthError(null);

        const { error } =
            authMode === "signUp"
                ? await supabase.auth.signUp({ email: authEmail.trim(), password: authPassword })
                : await supabase.auth.signInWithPassword({ email: authEmail.trim(), password: authPassword });

        if (error) {
            setAuthError(error.message);
        } else {
            setAuthEmail("");
            setAuthPassword("");
        }
        setAuthSubmitting(false);
    };

    const handleSignOut = async () => {
        await supabase.auth.signOut();
    };

    // --- UI Components ---
    const renderCarCard = (car: any) => {
        const isFavorited = favoriteListingIds.has(car.id);
        return (
            <div
                key={car.id}
                className="flex flex-col bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm hover:shadow-md transition-shadow"
            >
                {/* Image Section */}
                <div className="h-48 bg-slate-100 flex items-center justify-center border-b border-slate-100 overflow-hidden relative">
                    {car.is_good_deal && (
                        <span className="absolute top-2 left-2 z-10 bg-amber-400 text-amber-950 text-xs font-bold px-2 py-1 rounded-full shadow">
                            🔥 Good Deal
                            {typeof car.deal_score === "number"
                                ? ` · ${Math.round(car.deal_score * 100)}% off`
                                : ""}
                        </span>
                    )}
                    {user && (
                        <button
                            onClick={() => handleToggleFavorite(car)}
                            aria-label={
                                isFavorited
                                    ? `Remove ${car.model_year} ${car.make} ${car.model} from favorites`
                                    : `Add ${car.model_year} ${car.make} ${car.model} to favorites`
                            }
                            className="absolute top-2 right-2 z-10 w-8 h-8 flex items-center justify-center bg-white/90 rounded-full shadow hover:bg-white transition text-lg"
                        >
                            {isFavorited ? "❤️" : "🤍"}
                        </button>
                    )}
                    {car.photos && car.photos.length > 0 ? (
                        <Image
                            src={car.photos[0]}
                            alt={`${car.model_year} ${car.make} ${car.model}`}
                            fill
                            className="object-cover"
                            sizes="(max-width: 768px) 100vw, (max-width: 1200px) 50vw, 33vw"
                        />
                    ) : (
                        <span className="text-slate-400 text-sm font-medium">
                            NO IMAGE
                        </span>
                    )}
                </div>
                <div className="p-5 flex flex-col flex-1">
                    <div className="flex justify-between items-start mb-3">
                        <h2 className="text-lg font-bold text-slate-900 leading-tight">
                            {car.model_year} {car.make} {car.model}
                        </h2>
                        <span className="text-lg font-bold text-emerald-600">
                            ${car.price?.toLocaleString()}
                        </span>
                    </div>

                    <div className="space-y-1 mb-6 flex-1 text-sm text-slate-600">
                        <p>
                            {car.mileage
                                ? `${car.mileage.toLocaleString()} miles`
                                : "Mileage not listed"}
                        </p>
                        <p>
                            Source:{" "}
                            <span className="font-medium text-slate-800">
                                {getSellerLabel(car)}
                            </span>
                        </p>
                        {formatLastSeen(car.last_seen_at) && (
                            <p className="text-xs text-slate-400">
                                {formatLastSeen(car.last_seen_at)}
                            </p>
                        )}
                    </div>

                    <a
                        href={car.original_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="w-full text-center bg-slate-900 text-white font-medium py-2.5 rounded-lg hover:bg-slate-800 transition"
                    >
                        View Listing
                    </a>
                </div>
            </div>
        );
    };

    const renderListings = () => {
        if (loading) {
            return (
                <div className="py-12 text-center">
                    <p className="text-slate-500 font-medium animate-pulse">
                        Scanning inventory...
                    </p>
                </div>
            );
        }

        if (error) {
            return (
                <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-center">
                    <p>Error: {error}</p>
                </div>
            );
        }

        if (listings.length === 0) {
            return (
                <div className="py-16 text-center bg-white border border-slate-200 border-dashed rounded-xl shadow-sm">
                    <p className="text-slate-500 text-lg mb-4">
                        No vehicles found matching your criteria.
                    </p>
                    <button
                        onClick={handleClearFilters}
                        className="text-blue-600 font-semibold hover:text-blue-800 transition"
                    >
                        Clear filters and try again
                    </button>
                </div>
            );
        }

        return (
            <>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                    {listings.map((car) => renderCarCard(car))}
                </div>
                {hasMore && (
                    <div className="flex justify-center mt-8">
                        <button
                            onClick={handleLoadMore}
                            disabled={loadingMore}
                            className="bg-white border border-slate-300 text-slate-900 font-semibold py-2.5 px-8 rounded-lg hover:bg-slate-50 transition disabled:opacity-60"
                        >
                            {loadingMore ? "Loading..." : "Load More"}
                        </button>
                    </div>
                )}
            </>
        );
    };

    return (
        <main className="min-h-screen bg-slate-50 p-4 md:p-8 font-sans">
            <div className="max-w-5xl mx-auto space-y-8">
                {/* Header Section */}
                <header>
                    <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">
                        Used Car Finder
                    </h1>
                    <p className="text-slate-500 mt-2">
                        Discover and track local inventory across multiple
                        marketplaces.
                    </p>
                </header>

                <MonitoringStats supabase={supabase} />

                {/* Search & Filter Card */}
                <section className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                    <form onSubmit={handleSearch} className="space-y-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <MultiSelectDropdown
                                id="make"
                                label="Make"
                                options={availableMakes}
                                selected={make}
                                onChange={setMake}
                            />
                            <MultiSelectDropdown
                                id="model"
                                label="Model"
                                options={availableModels}
                                selected={model}
                                onChange={setModel}
                            />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label
                                    htmlFor="transmission"
                                    className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    Transmission
                                </label>
                                <select
                                    id="transmission"
                                    value={transmission}
                                    onChange={(e) => setTransmission(e.target.value)}
                                    className={`w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition ${inputTextClass}`}
                                >
                                    <option value="">Any Transmission</option>
                                    {availableTransmissions.some(isAutomaticTransmission) && (
                                        <option value={ANY_AUTOMATIC_VALUE}>Any Automatic</option>
                                    )}
                                    {availableTransmissions.map((option) => (
                                        <option key={option} value={option}>
                                            {option}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <div>
                                <label
                                    htmlFor="sellerType"
                                    className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    Seller Type
                                </label>
                                <select
                                    id="sellerType"
                                    value={sellerType}
                                    onChange={(e) => setSellerType(e.target.value)}
                                    className={`w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition ${inputTextClass}`}
                                >
                                    <option value="">Any Seller Type</option>
                                    {availableSellerTypes.map((option) => (
                                        <option key={option} value={option}>
                                            {option}
                                        </option>
                                    ))}
                                </select>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            <div>
                                <label
                                    htmlFor="minYear"
                                    className="flex justify-between text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    <span>Min Year</span>
                                    <span className="text-slate-900 normal-case">{minYear}</span>
                                </label>
                                <input
                                    id="minYear"
                                    type="range"
                                    min={YEAR_MIN}
                                    max={YEAR_MAX}
                                    step={1}
                                    value={minYear}
                                    onChange={(e) => setMinYear(Number(e.target.value))}
                                    className="w-full accent-blue-600"
                                />
                                <div className="flex justify-between text-xs text-slate-400 mt-1">
                                    <span>{YEAR_MIN}</span>
                                    <span>{YEAR_MAX}</span>
                                </div>
                            </div>
                            <div>
                                <label
                                    htmlFor="maxMileage"
                                    className="flex justify-between text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    <span>Max Mileage</span>
                                    <span className="text-slate-900 normal-case">
                                        {maxMileage.toLocaleString()} mi
                                    </span>
                                </label>
                                <input
                                    id="maxMileage"
                                    type="range"
                                    min={0}
                                    max={MILEAGE_MAX}
                                    step={5000}
                                    value={maxMileage}
                                    onChange={(e) => setMaxMileage(Number(e.target.value))}
                                    className="w-full accent-blue-600"
                                />
                                <div className="flex justify-between text-xs text-slate-400 mt-1">
                                    <span>0</span>
                                    <span>{MILEAGE_MAX.toLocaleString()}</span>
                                </div>
                            </div>
                            <div>
                                <label
                                    htmlFor="maxPrice"
                                    className="flex justify-between text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    <span>Max Price</span>
                                    <span className="text-slate-900 normal-case">
                                        ${maxPrice.toLocaleString()}
                                    </span>
                                </label>
                                <input
                                    id="maxPrice"
                                    type="range"
                                    min={0}
                                    max={PRICE_MAX}
                                    step={1000}
                                    value={maxPrice}
                                    onChange={(e) => setMaxPrice(Number(e.target.value))}
                                    className="w-full accent-blue-600"
                                />
                                <div className="flex justify-between text-xs text-slate-400 mt-1">
                                    <span>$0</span>
                                    <span>${PRICE_MAX.toLocaleString()}</span>
                                </div>
                            </div>
                        </div>

                        <div className="flex justify-end">
                            <button
                                type="submit"
                                className="w-full md:w-auto bg-slate-900 text-white font-bold py-3 px-8 rounded-lg hover:bg-slate-800 transition shadow-sm"
                            >
                                Search
                            </button>
                        </div>
                    </form>
                </section>

                {/* Save Search Alert Card */}
                <section className="bg-blue-50 border border-blue-200 p-6 rounded-2xl shadow-sm">
                    {!user ? (
                        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                            <div>
                                <h3 className="text-blue-900 font-bold text-lg">
                                    Don't see what you want?
                                </h3>
                                <p className="text-blue-700 text-sm mt-1">
                                    Log in to save a search and we'll email you
                                    when a match is posted.
                                </p>
                            </div>

                            <div className="w-full md:w-auto">
                                <form
                                    onSubmit={handleAuthSubmit}
                                    className="flex flex-col md:flex-row w-full md:w-auto gap-3"
                                >
                                    <input
                                        type="email"
                                        placeholder="Email address"
                                        value={authEmail}
                                        onChange={(e) => setAuthEmail(e.target.value)}
                                        required
                                        className={`flex-1 md:w-56 border border-blue-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm ${inputTextClass}`}
                                    />
                                    <input
                                        type="password"
                                        placeholder="Password"
                                        value={authPassword}
                                        onChange={(e) => setAuthPassword(e.target.value)}
                                        required
                                        minLength={6}
                                        className={`flex-1 md:w-48 border border-blue-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm ${inputTextClass}`}
                                    />
                                    <button
                                        type="submit"
                                        disabled={authSubmitting}
                                        className="font-bold py-3 px-6 rounded-lg text-sm whitespace-nowrap transition bg-blue-600 hover:bg-blue-700 text-white disabled:opacity-60"
                                    >
                                        {authSubmitting
                                            ? "..."
                                            : authMode === "signUp"
                                              ? "Sign Up"
                                              : "Log In"}
                                    </button>
                                </form>
                                <p className="text-blue-700 text-xs mt-2 text-right">
                                    {authMode === "signUp" ? "Already have an account? " : "New here? "}
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setAuthMode(authMode === "signUp" ? "signIn" : "signUp");
                                            setAuthError(null);
                                        }}
                                        className="font-semibold underline"
                                    >
                                        {authMode === "signUp" ? "Log in" : "Sign up"}
                                    </button>
                                </p>
                                {authError && (
                                    <p className="text-red-600 text-xs mt-1 text-right">{authError}</p>
                                )}
                            </div>
                        </div>
                    ) : (
                        <>
                            <div className="flex flex-col md:flex-row items-center justify-between gap-4 mb-4">
                                <div>
                                    <h3 className="text-blue-900 font-bold text-lg">
                                        Don't see what you want?
                                    </h3>
                                    <p className="text-blue-700 text-sm mt-1">
                                        Save these exact filters and we'll
                                        email you when a match is posted.
                                    </p>
                                </div>
                                <div className="text-sm text-blue-700 flex items-center gap-3 whitespace-nowrap">
                                    <span>
                                        Signed in as{" "}
                                        <span className="font-semibold">{user.email}</span>
                                    </span>
                                    <button
                                        onClick={handleSignOut}
                                        className="text-blue-900 font-semibold hover:underline"
                                    >
                                        Log out
                                    </button>
                                </div>
                            </div>

                            {editingSearchId && (
                                <div className="flex items-center justify-between gap-3 mb-3 p-2 bg-blue-100 rounded-lg text-sm text-blue-900">
                                    <span>
                                        Editing <span className="font-semibold">{searchName || "Unnamed search"}</span> — change the filters above, then Update.
                                    </span>
                                    <button
                                        type="button"
                                        onClick={handleCancelEdit}
                                        className="font-semibold underline whitespace-nowrap"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            )}

                            <div className="flex items-center gap-4 text-sm text-blue-900 mb-3">
                                <span className="font-semibold">Group emails by:</span>
                                {(["combined", "make", "model"] as const).map((option) => (
                                    <label key={option} className="flex items-center gap-1 cursor-pointer capitalize">
                                        <input
                                            type="radio"
                                            name="notificationGrouping"
                                            value={option}
                                            checked={notificationGrouping === option}
                                            onChange={() => setNotificationGrouping(option)}
                                        />
                                        {option}
                                    </label>
                                ))}
                            </div>

                            <form
                                onSubmit={handleSaveSearch}
                                className="flex flex-col md:flex-row w-full gap-3"
                            >
                                <input
                                    type="text"
                                    placeholder="Name this search (e.g. Lexus ES)"
                                    value={searchName}
                                    onChange={(e) => setSearchName(e.target.value)}
                                    className={`flex-1 md:w-56 border border-blue-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm ${inputTextClass}`}
                                />
                                <input
                                    type="email"
                                    placeholder="Enter your email"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className={`flex-1 md:w-64 border border-blue-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm ${inputTextClass}`}
                                />
                                <button
                                    type="submit"
                                    disabled={
                                        saveStatus === "loading" ||
                                        saveStatus === "success"
                                    }
                                    className={`font-bold py-3 px-6 rounded-lg text-sm whitespace-nowrap transition ${
                                        saveStatus === "success"
                                            ? "bg-green-600 hover:bg-green-700 text-white"
                                            : saveStatus === "error"
                                              ? "bg-red-600 hover:bg-red-700 text-white"
                                              : "bg-blue-600 hover:bg-blue-700 text-white"
                                    }`}
                                >
                                    {saveStatus === "loading"
                                        ? editingSearchId
                                            ? "Updating..."
                                            : "Saving..."
                                        : saveStatus === "success"
                                          ? editingSearchId
                                              ? "Updated!"
                                              : "Saved!"
                                          : saveStatus === "error"
                                            ? "Error"
                                            : editingSearchId
                                              ? "Update Search"
                                              : "Save Search"}
                                </button>
                            </form>
                        </>
                    )}
                </section>

                {/* My Saved Searches */}
                {mySavedSearches.length > 0 && (
                    <section className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                        <button
                            type="button"
                            onClick={() => setSavedSearchesExpanded((prev) => !prev)}
                            aria-expanded={savedSearchesExpanded}
                            className="w-full flex items-center justify-between text-left"
                        >
                            <h3 className="font-bold text-slate-900 text-lg">
                                My Saved Searches ({mySavedSearches.length})
                            </h3>
                            <span className="text-slate-400 text-sm font-medium whitespace-nowrap">
                                {savedSearchesExpanded ? "Hide ▲" : "Show ▼"}
                            </span>
                        </button>
                        {savedSearchesExpanded && (
                        <ul className="space-y-3 mt-4">
                            {mySavedSearches.map((search) => (
                                <li
                                    key={search.id}
                                    className="flex items-center justify-between gap-4 p-3 border border-slate-200 rounded-lg"
                                >
                                    <div>
                                        <p className="font-semibold text-slate-900">
                                            {search.name || "Unnamed search"}
                                            {search.is_active === false && (
                                                <span className="ml-2 text-xs font-medium text-slate-400">
                                                    (Paused)
                                                </span>
                                            )}
                                        </p>
                                        <p className="text-sm text-slate-500">
                                            {describeSavedSearch(search)} — {search.email}
                                        </p>
                                    </div>
                                    <div className="flex items-center gap-3 whitespace-nowrap">
                                        <button
                                            onClick={() => handleEditSavedSearch(search)}
                                            aria-label={`Edit ${search.name || "Unnamed search"}`}
                                            className="text-blue-600 font-semibold text-sm hover:text-blue-800 transition"
                                        >
                                            Edit
                                        </button>
                                        <button
                                            onClick={() => handleToggleSavedSearchActive(search)}
                                            aria-label={`${search.is_active === false ? "Resume" : "Pause"} ${search.name || "Unnamed search"}`}
                                            className="text-slate-600 font-semibold text-sm hover:text-slate-900 transition"
                                        >
                                            {search.is_active === false ? "Resume" : "Pause"}
                                        </button>
                                        <button
                                            onClick={() => handleDeleteSavedSearch(search.id)}
                                            aria-label={`Delete ${search.name || "Unnamed search"}`}
                                            className="text-red-600 font-semibold text-sm hover:text-red-800 transition"
                                        >
                                            Delete
                                        </button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                        )}
                    </section>
                )}

                {/* My Favorites */}
                {myFavorites.length > 0 && (
                    <section className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                        <button
                            type="button"
                            onClick={() => setFavoritesExpanded((prev) => !prev)}
                            aria-expanded={favoritesExpanded}
                            className="w-full flex items-center justify-between text-left"
                        >
                            <h3 className="font-bold text-slate-900 text-lg">
                                My Favorites ({myFavorites.length})
                            </h3>
                            <span className="text-slate-400 text-sm font-medium whitespace-nowrap">
                                {favoritesExpanded ? "Hide ▲" : "Show ▼"}
                            </span>
                        </button>
                        {favoritesExpanded && (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mt-4">
                            {myFavorites.map((car) => renderCarCard(car))}
                        </div>
                        )}
                    </section>
                )}

                {/* Results Grid */}
                <section>
                    <div className="flex justify-end items-center gap-2 mb-4">
                        <span className="group relative inline-flex">
                            <span
                                aria-label="What counts as Best Deal?"
                                className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-slate-200 text-slate-600 text-xs font-bold cursor-help"
                            >
                                i
                            </span>
                            <span className="pointer-events-none absolute right-0 top-full mt-1.5 w-64 max-w-[calc(100vw-2rem)] rounded-md bg-slate-900 px-2.5 py-2 text-xs font-normal leading-snug text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 z-20">
                                Best Deal ranks listings 12%+ below the median price of similar active listings (same make/model, within 2 model years and 20,000 miles).
                            </span>
                        </span>
                        <label htmlFor="sortBy" className="sr-only">
                            Sort by
                        </label>
                        <select
                            id="sortBy"
                            value={sortBy}
                            onChange={(e) => setSortBy(e.target.value as (typeof SORT_OPTIONS)[number]["value"])}
                            className={`border border-slate-300 p-2 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition ${inputTextClass}`}
                        >
                            {SORT_OPTIONS.map((option) => (
                                <option key={option.value} value={option.value}>
                                    Sort: {option.label}
                                </option>
                            ))}
                        </select>
                    </div>
                    {renderListings()}
                </section>
            </div>
        </main>
    );
}
