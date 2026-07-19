"use client";

import { useState, useEffect, useCallback } from "react";
import { createClient } from "@/utils/supabase/client";
import Image from "next/image";

const YEAR_MIN = 1990;
const YEAR_MAX = new Date().getFullYear();
const MILEAGE_MAX = 200000;
const PRICE_MAX = 100000;

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

function describeSavedSearch(search: any) {
    const parts = [];
    if (search.make) parts.push(search.make);
    if (search.model) parts.push(search.model);
    const vehicle = parts.length > 0 ? parts.join(" ") : "Any vehicle";

    const filters = [];
    if (search.min_year) filters.push(`${search.min_year}+`);
    if (search.max_mileage) filters.push(`under ${search.max_mileage.toLocaleString()} mi`);
    if (search.max_price) filters.push(`under $${search.max_price.toLocaleString()}`);

    return filters.length > 0 ? `${vehicle} — ${filters.join(", ")}` : vehicle;
}

export default function Home() {
    const supabase = createClient();

    // --- Filter State ---
    const [make, setMake] = useState("");
    const [model, setModel] = useState("");
    const [minYear, setMinYear] = useState(YEAR_MIN);
    const [maxMileage, setMaxMileage] = useState(MILEAGE_MAX);
    const [maxPrice, setMaxPrice] = useState(PRICE_MAX);
    const [sortBy, setSortBy] = useState<(typeof SORT_OPTIONS)[number]["value"]>("best_deal");

    // --- Data State ---
    const [listings, setListings] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // --- Save Search State ---
    const [searchName, setSearchName] = useState("");
    const [email, setEmail] = useState("");
    const [saveStatus, setSaveStatus] = useState<
        "idle" | "loading" | "success" | "error"
    >("idle");
    const [mySavedSearches, setMySavedSearches] = useState<any[]>([]);

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
    const fetchListings = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const sortOption = SORT_OPTIONS.find((option) => option.value === sortBy) ?? SORT_OPTIONS[0];

            // last_seen_at is a tiebreaker only, not a sort option of its
            // own: when the primary sort has ties (e.g. two listings at
            // the same price), the one the scraper most recently
            // reconfirmed is more likely still available (see
            // scraper/staleness.py) and is preferred.
            let query = supabase
                .from("listings")
                .select("*")
                .eq("status", "active")
                .is("duplicate_of", null)
                .order(sortOption.column, { ascending: sortOption.ascending, nullsFirst: false })
                .order("last_seen_at", { ascending: false, nullsFirst: false });

            if (make.trim()) query = query.ilike("make", `%${make.trim()}%`);
            if (model.trim()) query = query.ilike("model", `%${model.trim()}%`);
            if (minYear > YEAR_MIN) query = query.gte("model_year", minYear);
            if (maxMileage < MILEAGE_MAX) query = query.lte("mileage", maxMileage);
            if (maxPrice < PRICE_MAX) query = query.lte("price", maxPrice);

            const { data, error: fetchError } = await query.limit(50);

            if (fetchError) throw fetchError;
            setListings(data || []);
        } catch (err: any) {
            setError(err.message || "Failed to fetch listings.");
        } finally {
            setLoading(false);
        }
    }, [make, model, minYear, maxMileage, maxPrice, sortBy, supabase]);

    useEffect(() => {
        fetchListings();
    }, [fetchListings]);

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

    // --- Handlers ---
    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        fetchListings();
    };

    const handleClearFilters = () => {
        setMake("");
        setModel("");
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
            !make.trim() &&
            !model.trim() &&
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

        const { data, error } = await supabase
            .from("saved_searches")
            .insert({
                user_id: user.id,
                name: searchName.trim() || null,
                email: email.trim(),
                make: make.trim() || null,
                model: model.trim() || null,
                min_year: minYear > YEAR_MIN ? minYear : null,
                max_mileage: maxMileage < MILEAGE_MAX ? maxMileage : null,
                max_price: maxPrice < PRICE_MAX ? maxPrice : null,
            })
            .select()
            .single();

        if (error) {
            console.error("Supabase Insert Error:", error);
            setSaveStatus("error");
            setTimeout(() => setSaveStatus("idle"), 3000);
        } else {
            setSaveStatus("success");
            setSearchName("");
            if (data?.id) {
                setMySavedSearches((prev) => [...prev, data]);
            }
            setTimeout(() => setSaveStatus("idle"), 3000);
        }
    };

    const handleDeleteSavedSearch = async (id: string) => {
        const { error } = await supabase.from("saved_searches").delete().eq("id", id);
        if (error) {
            console.error("Supabase Delete Error:", error);
            return;
        }
        setMySavedSearches((prev) => prev.filter((search) => search.id !== id));
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
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {listings.map((car) => (
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
                ))}
            </div>
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

                {/* Search & Filter Card */}
                <section className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                    <form onSubmit={handleSearch} className="space-y-6">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label
                                    htmlFor="make"
                                    className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    Make
                                </label>
                                <input
                                    id="make"
                                    type="text"
                                    placeholder="e.g. Toyota"
                                    value={make}
                                    onChange={(e) => setMake(e.target.value)}
                                    className={`w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition ${inputTextClass}`}
                                />
                            </div>
                            <div>
                                <label
                                    htmlFor="model"
                                    className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    Model
                                </label>
                                <input
                                    id="model"
                                    type="text"
                                    placeholder="e.g. Tacoma"
                                    value={model}
                                    onChange={(e) => setModel(e.target.value)}
                                    className={`w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition ${inputTextClass}`}
                                />
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
                                        ? "Saving..."
                                        : saveStatus === "success"
                                          ? "Saved!"
                                          : saveStatus === "error"
                                            ? "Error"
                                            : "Save Search"}
                                </button>
                            </form>
                        </>
                    )}
                </section>

                {/* My Saved Searches */}
                {mySavedSearches.length > 0 && (
                    <section className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                        <h3 className="font-bold text-slate-900 text-lg mb-4">
                            My Saved Searches
                        </h3>
                        <ul className="space-y-3">
                            {mySavedSearches.map((search) => (
                                <li
                                    key={search.id}
                                    className="flex items-center justify-between gap-4 p-3 border border-slate-200 rounded-lg"
                                >
                                    <div>
                                        <p className="font-semibold text-slate-900">
                                            {search.name || "Unnamed search"}
                                        </p>
                                        <p className="text-sm text-slate-500">
                                            {describeSavedSearch(search)} — {search.email}
                                        </p>
                                    </div>
                                    <button
                                        onClick={() => handleDeleteSavedSearch(search.id)}
                                        aria-label={`Delete ${search.name || "Unnamed search"}`}
                                        className="text-red-600 font-semibold text-sm hover:text-red-800 transition whitespace-nowrap"
                                    >
                                        Delete
                                    </button>
                                </li>
                            ))}
                        </ul>
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
