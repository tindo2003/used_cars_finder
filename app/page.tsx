"use client";

import { useState, useEffect, useCallback } from "react";
import { createClient } from "@/utils/supabase/client";
import Image from "next/image";

export default function Home() {
    const supabase = createClient();

    // --- Filter State ---
    const [make, setMake] = useState("");
    const [model, setModel] = useState("");
    const [minYear, setMinYear] = useState("");
    const [maxMileage, setMaxMileage] = useState("");
    const [maxPrice, setMaxPrice] = useState("");

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

    // --- Core Logic ---
    const fetchListings = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            let query = supabase
                .from("listings")
                .select("*")
                .eq("status", "active")
                .order("posted_at", { ascending: false });

            if (make.trim()) query = query.ilike("make", `%${make.trim()}%`);
            if (model.trim()) query = query.ilike("model", `%${model.trim()}%`);
            if (minYear.trim()) query = query.gte("model_year", parseInt(minYear));
            if (maxMileage.trim()) query = query.lte("mileage", parseInt(maxMileage));
            if (maxPrice.trim()) query = query.lte("price", parseInt(maxPrice));

            const { data, error: fetchError } = await query.limit(50);

            if (fetchError) throw fetchError;
            setListings(data || []);
        } catch (err: any) {
            setError(err.message || "Failed to fetch listings.");
        } finally {
            setLoading(false);
        }
    }, [make, model, minYear, maxMileage, maxPrice, supabase]);

    useEffect(() => {
        fetchListings();
    }, [fetchListings]);

    // --- Handlers ---
    const handleSearch = (e: React.FormEvent) => {
        e.preventDefault();
        fetchListings();
    };

    const handleClearFilters = () => {
        setMake("");
        setModel("");
        setMinYear("");
        setMaxMileage("");
        setMaxPrice("");
    };

    const handleSaveSearch = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!email) {
            alert("Please enter an email address first.");
            return;
        }

        setSaveStatus("loading");

        const { error } = await supabase.from("saved_searches").insert({
            name: searchName.trim() || null,
            email: email.trim(),
            make: make.trim() || null,
            model: model.trim() || null,
            min_year: minYear ? parseInt(minYear) : null,
            max_mileage: maxMileage ? parseInt(maxMileage) : null,
            max_price: maxPrice ? parseInt(maxPrice) : null,
        });

        if (error) {
            console.error("Supabase Insert Error:", error);
            setSaveStatus("error");
            setTimeout(() => setSaveStatus("idle"), 3000);
        } else {
            setSaveStatus("success");
            setSearchName("");
            setTimeout(() => setSaveStatus("idle"), 3000);
        }
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
                                <p className="capitalize">
                                    Source:{" "}
                                    <span className="font-medium text-slate-800">
                                        {car.marketplace_source}
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
                    <form onSubmit={handleSearch} className="space-y-4">
                        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
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
                                    className="w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
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
                                    className="w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
                                />
                            </div>
                            <div>
                                <label
                                    htmlFor="minYear"
                                    className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    Min Year
                                </label>
                                <input
                                    id="minYear"
                                    type="number"
                                    placeholder="e.g. 2018"
                                    value={minYear}
                                    onChange={(e) => setMinYear(e.target.value)}
                                    className="w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
                                />
                            </div>
                            <div>
                                <label
                                    htmlFor="maxMileage"
                                    className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    Max Mileage
                                </label>
                                <input
                                    id="maxMileage"
                                    type="number"
                                    placeholder="e.g. 60000"
                                    value={maxMileage}
                                    onChange={(e) => setMaxMileage(e.target.value)}
                                    className="w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
                                />
                            </div>
                            <div>
                                <label
                                    htmlFor="maxPrice"
                                    className="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-2"
                                >
                                    Max Price
                                </label>
                                <input
                                    id="maxPrice"
                                    type="number"
                                    placeholder="$"
                                    value={maxPrice}
                                    onChange={(e) => setMaxPrice(e.target.value)}
                                    className="w-full border border-slate-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
                                />
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
                <section className="bg-blue-50 border border-blue-200 p-6 rounded-2xl shadow-sm flex flex-col md:flex-row items-center justify-between gap-4">
                    <div>
                        <h3 className="text-blue-900 font-bold text-lg">
                            Don't see what you want?
                        </h3>
                        <p className="text-blue-700 text-sm mt-1">
                            Save these exact filters and we'll email you when a
                            match is posted.
                        </p>
                    </div>

                    <form
                        onSubmit={handleSaveSearch}
                        className="flex flex-col md:flex-row w-full md:w-auto gap-3"
                    >
                        <input
                            type="text"
                            placeholder="Name this search (e.g. Lexus ES)"
                            value={searchName}
                            onChange={(e) => setSearchName(e.target.value)}
                            className="flex-1 md:w-56 border border-blue-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm"
                        />
                        <input
                            type="email"
                            required
                            placeholder="Enter your email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="flex-1 md:w-64 border border-blue-300 p-3 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none text-sm"
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
                </section>

                {/* Results Grid */}
                <section>{renderListings()}</section>
            </div>
        </main>
    );
}
