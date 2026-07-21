import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Home from "./page";

const { getFakeSupabase, setFakeSupabase } = vi.hoisted(() => {
    let current: any = null;
    return {
        getFakeSupabase: () => current,
        setFakeSupabase: (value: any) => {
            current = value;
        },
    };
});

vi.mock("@/utils/supabase/client", () => ({
    createClient: () => getFakeSupabase(),
}));

vi.mock("next/image", () => ({
    default: (props: any) => <img {...props} />,
}));

function makeListing(overrides: Record<string, unknown> = {}) {
    return {
        id: "listing-1",
        marketplace_source: "dealeron",
        original_url: "https://example.com/listing-1",
        make: "Toyota",
        model: "Camry",
        model_year: 2022,
        price: 21000,
        mileage: 30000,
        photos: [],
        ...overrides,
    };
}

function makeListings(count: number, idPrefix: string) {
    return Array.from({ length: count }, (_, i) =>
        makeListing({
            id: `${idPrefix}-${i}`,
            original_url: `https://example.com/${idPrefix}-${i}`,
            model: `Camry-${idPrefix}-${i}`,
        })
    );
}

type SavedSearchPayload = {
    name: string | null;
    email: string;
    make: string[] | null;
    model: string[] | null;
    min_year: number | null;
    max_mileage: number | null;
    max_price: number | null;
    notification_grouping: string;
};

// A logged-in test user with no email set, so page.tsx's "prefill the
// digest email from the account" effect stays a no-op -- tests that
// type their own value into the email field don't have to clear it
// first. LOGGED_IN_USER_WITH_EMAIL below covers the prefill behavior
// itself.
const LOGGED_IN_USER = { id: "user-1", email: "" };
const LOGGED_IN_USER_WITH_EMAIL = { id: "user-1", email: "owner@example.com" };

function makeFakeSupabase({
    listingsResult = { data: [makeListing()], error: null },
    // Backs the make/model multi-select options (a separate,
    // unfiltered `select("make, model")` query) -- defaults to the
    // same data as listingsResult so most tests don't need to think
    // about it, but can be overridden independently for tests that
    // need options to exist even when the (filtered) listingsResult is
    // empty, e.g. testing "clear filters" from a no-results state.
    filterOptionsResult = listingsResult,
    // What a "Load More" click's .range() call resolves to (any .range
    // call with a nonzero starting index) -- separate from
    // listingsResult (the initial page, .range(0, ...)) so tests can
    // assert a second batch actually gets appended, not re-fetched.
    loadMoreResult = { data: [] as unknown[], error: null },
    // Backs the MonitoringStats widget's single stats query (id/
    // created_at/last_seen_at/dealer_name/marketplace_source columns).
    // Defaults to empty so the widget quietly renders nothing unless a
    // test opts in.
    statsResult = { data: [] as unknown[], error: null },
    insertResult = { data: { id: "search-1" }, error: null },
    updateResult = { data: null as unknown, error: null as unknown },
    savedSearchesSelectResult = { data: [], error: null },
    deleteResult = { error: null },
    favoritesSelectResult = { data: [] as { listings: unknown }[], error: null },
    favoriteInsertResult = { error: null as { message: string } | null },
    favoriteDeleteResult = { error: null as { message: string } | null },
    authUser = null as { id: string; email: string } | null,
    signInResult = { error: null as { message: string } | null },
    signUpResult = { error: null as { message: string } | null },
    onInsert,
    onUpdate,
    onDelete,
    onFavoriteInsert,
    onFavoriteDelete,
}: {
    listingsResult?: { data: unknown[]; error: unknown };
    filterOptionsResult?: { data: unknown[]; error: unknown };
    loadMoreResult?: { data: unknown[]; error: unknown };
    statsResult?: { data: unknown[]; error: unknown };
    insertResult?: { data?: unknown; error: unknown };
    updateResult?: { data?: unknown; error: unknown };
    savedSearchesSelectResult?: { data: unknown[]; error: unknown };
    deleteResult?: { error: unknown };
    favoritesSelectResult?: { data: { listings: unknown }[]; error: unknown };
    favoriteInsertResult?: { error: { message: string } | null };
    favoriteDeleteResult?: { error: { message: string } | null };
    authUser?: { id: string; email: string } | null;
    signInResult?: { error: { message: string } | null };
    signUpResult?: { error: { message: string } | null };
    onInsert?: (payload: SavedSearchPayload) => void;
    onUpdate?: (id: unknown, payload: Record<string, unknown>) => void;
    onDelete?: (id: unknown) => void;
    onFavoriteInsert?: (payload: { user_id: string; listing_id: string }) => void;
    onFavoriteDelete?: (userId: unknown, listingId: unknown) => void;
} = {}) {
    function makeChainable(result: unknown, methods: string[]) {
        const chain: any = {};
        for (const method of methods) {
            chain[method] = vi.fn(() => chain);
        }
        chain.then = (resolve: (value: unknown) => void) => resolve(result);
        return chain;
    }

    const listingsQuery = makeChainable(listingsResult, ["eq", "is", "order", "or", "ilike", "gte", "lte", "limit"]);
    // .range()'s resolved value depends on its args (the initial fetch
    // is .range(0, ...); "Load More" is .range(<current count>, ...))
    // rather than being a fixed chainable method, so it needs its own
    // mock instead of the generic makeChainable pattern.
    listingsQuery.range = vi.fn((from: number, _to: number) => {
        listingsQuery.then = (resolve: (value: unknown) => void) => resolve(from === 0 ? listingsResult : loadMoreResult);
        return listingsQuery;
    });
    const filterOptionsQuery = makeChainable(filterOptionsResult, ["eq"]);

    // MonitoringStats no longer runs one query over full listing rows --
    // it does 3 cheap aggregate queries (2 counts + an order/limit(1))
    // plus one paginated-but-skinny-columns query for distinct sources.
    // All 4 are derived here from the same statsResult.data fixture so
    // existing tests don't need to know about the split.
    const statsRows = (statsResult.data ?? []) as any[];
    const startOfTodayForStats = new Date();
    startOfTodayForStats.setHours(0, 0, 0, 0);
    const newTodayCount = statsRows.filter(
        (row) => row.created_at && new Date(row.created_at) >= startOfTodayForStats
    ).length;
    const lastCrawlRow = statsRows.reduce<any>((latest, row) => {
        if (!row.last_seen_at) return latest;
        if (!latest || new Date(row.last_seen_at) > new Date(latest.last_seen_at)) return row;
        return latest;
    }, null);

    // A fresh chain per call (not a shared singleton) so the plain count
    // and the .gte()-filtered "new today" count -- both built from the
    // same activeFilter() factory in page.tsx -- don't collide.
    function makeCountQuery(count: number): any {
        const chain: any = {};
        chain.eq = vi.fn(() => chain);
        chain.is = vi.fn(() => chain);
        chain.gte = vi.fn(() => makeCountQuery(newTodayCount));
        chain.then = (resolve: (value: unknown) => void) => resolve({ count, error: statsResult.error });
        return chain;
    }

    const lastCrawlQuery = makeChainable(
        { data: lastCrawlRow ? [{ last_seen_at: lastCrawlRow.last_seen_at }] : [], error: statsResult.error },
        ["eq", "is", "order", "limit"]
    );

    const sourceQuery = makeChainable(
        {
            data: statsRows.map((row) => ({
                dealer_name: row.dealer_name,
                marketplace_source: row.marketplace_source,
            })),
            error: statsResult.error,
        },
        ["eq", "is", "order"]
    );
    sourceQuery.range = vi.fn(() => sourceQuery);

    // page.tsx issues several different `listings` queries: the main
    // `select("*")` fetch (filtered, sorted, paginated), a separate
    // unfiltered fetch of just filter-option columns (make/model/
    // transmission/seller_type), and MonitoringStats' own queries.
    // Branch on the columns argument so each gets its own mock
    // chain/result.
    const listingsTable = {
        select: vi.fn((columns: string) => {
            if (columns === "*") return listingsQuery;
            if (columns === "id") return makeCountQuery(statsRows.length);
            if (columns === "last_seen_at") return lastCrawlQuery;
            if (columns === "dealer_name, marketplace_source") return sourceQuery;
            return filterOptionsQuery;
        }),
    };

    const savedSearchesTable = {
        insert: vi.fn((payload: SavedSearchPayload) => {
            onInsert?.(payload);
            return makeChainable(insertResult, ["select", "single"]);
        }),
        update: vi.fn((payload: Record<string, unknown>) => {
            const chain: any = {};
            chain.eq = vi.fn((_column: string, id: unknown) => {
                onUpdate?.(id, payload);
                return makeChainable(updateResult, ["select", "single"]);
            });
            return chain;
        }),
        select: vi.fn(() => makeChainable(savedSearchesSelectResult, ["in", "eq"])),
        delete: vi.fn(() => {
            const chain = makeChainable(deleteResult, []);
            chain.eq = vi.fn((_column: string, value: unknown) => {
                onDelete?.(value);
                return chain;
            });
            return chain;
        }),
    };

    const favoritesTable = {
        select: vi.fn(() => makeChainable(favoritesSelectResult, ["eq"])),
        insert: vi.fn((payload: { user_id: string; listing_id: string }) => {
            onFavoriteInsert?.(payload);
            return Promise.resolve(favoriteInsertResult);
        }),
        delete: vi.fn(() => {
            const chain: any = {};
            let capturedUserId: unknown;
            chain.eq = vi.fn((column: string, value: unknown) => {
                if (column === "user_id") capturedUserId = value;
                if (column === "listing_id") onFavoriteDelete?.(capturedUserId, value);
                return chain;
            });
            chain.then = (resolve: (value: unknown) => void) => resolve(favoriteDeleteResult);
            return chain;
        }),
    };

    const from = vi.fn((table: string) => {
        if (table === "listings") return listingsTable;
        if (table === "saved_searches") return savedSearchesTable;
        if (table === "favorites") return favoritesTable;
        throw new Error(`Unexpected table: ${table}`);
    });

    // nearby_listings() (migrations/016) returns setof listings, so a
    // radius search reuses the same chainable listingsQuery object a plain
    // .from("listings").select("*") already uses -- identical .eq/.is/
    // .order/.range support and the same range()-keyed initial-vs-load-more
    // switching.
    const rpc = vi.fn((fn: string, _params: Record<string, unknown>) => {
        if (fn === "nearby_listings") return listingsQuery;
        throw new Error(`Unexpected rpc: ${fn}`);
    });

    // Mimics the real client closely enough for these tests: a
    // successful sign-in/sign-up fires the registered
    // onAuthStateChange listener with a session, just like the real
    // Supabase client does, since page.tsx relies on that listener
    // (not signIn/signUp's return value) to update its user state.
    let authChangeCallback: ((event: string, session: unknown) => void) | null = null;
    const auth = {
        getUser: vi.fn(() => Promise.resolve({ data: { user: authUser } })),
        onAuthStateChange: vi.fn((callback: (event: string, session: unknown) => void) => {
            authChangeCallback = callback;
            return { data: { subscription: { unsubscribe: vi.fn() } } };
        }),
        signInWithPassword: vi.fn(({ email }: { email: string; password: string }) => {
            if (!signInResult.error) {
                authChangeCallback?.("SIGNED_IN", { user: { id: "user-1", email } });
            }
            return Promise.resolve(signInResult);
        }),
        signUp: vi.fn(({ email }: { email: string; password: string }) => {
            if (!signUpResult.error) {
                authChangeCallback?.("SIGNED_IN", { user: { id: "user-1", email } });
            }
            return Promise.resolve(signUpResult);
        }),
        signOut: vi.fn(() => {
            authChangeCallback?.("SIGNED_OUT", null);
            return Promise.resolve({ error: null });
        }),
    };

    return { from, auth, rpc, listingsQuery, savedSearchesTable, favoritesTable };
}

beforeEach(() => {
    setFakeSupabase(makeFakeSupabase());
});

describe("monitoring stats", () => {
    it("shows source count, active listings, new today, and last crawl", async () => {
        const now = Date.now();
        const todayMorning = new Date();
        todayMorning.setHours(1, 0, 0, 0);
        const threeDaysAgo = new Date(now - 3 * 24 * 60 * 60 * 1000).toISOString();

        setFakeSupabase(
            makeFakeSupabase({
                statsResult: {
                    data: [
                        {
                            id: "1",
                            created_at: todayMorning.toISOString(),
                            last_seen_at: new Date(now - 5000).toISOString(),
                            dealer_name: "Capitol Honda",
                            marketplace_source: "dealerinspire",
                        },
                        {
                            id: "2",
                            created_at: threeDaysAgo,
                            last_seen_at: new Date(now - 60000).toISOString(),
                            dealer_name: "Capitol Honda",
                            marketplace_source: "dealerinspire",
                        },
                        {
                            id: "3",
                            created_at: threeDaysAgo,
                            last_seen_at: new Date(now - 120000).toISOString(),
                            dealer_name: null,
                            marketplace_source: "craigslist",
                        },
                    ],
                    error: null,
                },
            })
        );
        render(<Home />);

        const heading = await screen.findByText("Currently monitoring");
        const widget = heading.closest("section") as HTMLElement;

        // 2 distinct sources (Capitol Honda + craigslist), 3 active
        // listings total, 1 of them created today.
        expect(within(widget).getByText("2")).toBeInTheDocument();
        expect(within(widget).getByText("3")).toBeInTheDocument();
        expect(within(widget).getByText("1")).toBeInTheDocument();
        expect(within(widget).getByText(/just now|seconds ago/)).toBeInTheDocument();
    });

    it("does not render when there are no active listings to report on", async () => {
        setFakeSupabase(makeFakeSupabase({ statsResult: { data: [], error: null } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByText("Currently monitoring")).not.toBeInTheDocument();
    });
});

describe("search filters", () => {
    it("renders listing results from the initial fetch", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: {
                    data: [makeListing({ make: "Honda", model: "Civic", model_year: 2021, price: 18500, mileage: 25000 })],
                    error: null,
                },
            })
        );

        render(<Home />);

        expect(await screen.findByText("2021 Honda Civic")).toBeInTheDocument();
        expect(screen.getByText("$18,500")).toBeInTheDocument();
        expect(screen.getByText("25,000 miles")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "View Listing" })).toHaveAttribute(
            "href",
            "https://example.com/listing-1"
        );
    });

    it("shows a no-results message with a clear-filters action when nothing matches", async () => {
        setFakeSupabase(makeFakeSupabase({ listingsResult: { data: [], error: null } }));
        render(<Home />);

        expect(await screen.findByText("No vehicles found matching your criteria.")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Clear filters and try again" })).toBeInTheDocument();
    });

    it("lets the customer pick makes/models from the multi-select and submit the search", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({
            listingsResult: {
                data: [makeListing(), makeListing({ id: "listing-2", make: "Lexus", model: "ES" })],
                error: null,
            },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Lexus" }));
        await user.click(screen.getByLabelText("Model"));
        await user.click(screen.getByRole("checkbox", { name: "ES" }));
        await user.click(screen.getByRole("button", { name: "Search" }));

        await waitFor(() => {
            expect(fake.listingsQuery.or).toHaveBeenCalledWith("make.ilike.Lexus");
            expect(fake.listingsQuery.or).toHaveBeenCalledWith("model.ilike.ES");
        });
    });

    it("lets the customer filter by transmission and seller type", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({
            listingsResult: {
                data: [
                    makeListing({ transmission: "Automatic", seller_type: "dealer" }),
                    makeListing({
                        id: "listing-2",
                        make: "Honda",
                        model: "Civic",
                        transmission: "Manual",
                        seller_type: null,
                    }),
                ],
                error: null,
            },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.selectOptions(screen.getByLabelText("Transmission"), "Manual");
        await user.selectOptions(screen.getByLabelText("Seller Type"), "dealer");

        await waitFor(() => {
            expect(fake.listingsQuery.ilike).toHaveBeenCalledWith("transmission", "Manual");
            expect(fake.listingsQuery.ilike).toHaveBeenCalledWith("seller_type", "dealer");
        });
    });

    it("lets the customer pick 'Any Automatic' to match every automatic variant at once", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({
            filterOptionsResult: {
                data: [
                    { make: "Toyota", model: "Camry", transmission: "6-Speed Automatic ECT-i", seller_type: "dealer" },
                    { make: "Honda", model: "Civic", transmission: "Manual", seller_type: null },
                ],
                error: null,
            },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.getByRole("option", { name: "Any Automatic" })).toBeInTheDocument();

        await user.selectOptions(screen.getByLabelText("Transmission"), "Any Automatic");

        await waitFor(() => {
            expect(fake.listingsQuery.ilike).toHaveBeenCalledWith("transmission", "%automatic%");
        });
    });

    it("hides 'Any Automatic' when no automatic variant is available", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                filterOptionsResult: {
                    data: [{ make: "Honda", model: "Civic", transmission: "Manual", seller_type: null }],
                    error: null,
                },
            })
        );
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByRole("option", { name: "Any Automatic" })).not.toBeInTheDocument();
    });

    it("only offers transmission/seller-type options that actually appear in listings", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                filterOptionsResult: {
                    data: [
                        { make: "Toyota", model: "Camry", transmission: "Automatic", seller_type: "dealer" },
                        { make: "Honda", model: "Civic", transmission: "Manual", seller_type: null },
                    ],
                    error: null,
                },
            })
        );
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.getByRole("option", { name: "Automatic" })).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "Manual" })).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "dealer" })).toBeInTheDocument();
        expect(screen.queryByRole("option", { name: "private" })).not.toBeInTheDocument();
    });

    it("scopes the Transmission options to the selected make and model", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
                filterOptionsResult: {
                    data: [
                        { make: "Toyota", model: "Camry", transmission: "Automatic", seller_type: "dealer" },
                        { make: "Toyota", model: "Corolla", transmission: "CVT", seller_type: "dealer" },
                        { make: "Honda", model: "Civic", transmission: "Manual", seller_type: null },
                    ],
                    error: null,
                },
            })
        );
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        // Before picking a make, every transmission is available.
        expect(screen.getByRole("option", { name: "Automatic" })).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "CVT" })).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "Manual" })).toBeInTheDocument();

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));

        expect(screen.getByRole("option", { name: "Automatic" })).toBeInTheDocument();
        expect(screen.getByRole("option", { name: "CVT" })).toBeInTheDocument();
        expect(screen.queryByRole("option", { name: "Manual" })).not.toBeInTheDocument();

        await user.click(screen.getByLabelText("Model"));
        await user.click(screen.getByRole("checkbox", { name: "Camry" }));

        expect(screen.getByRole("option", { name: "Automatic" })).toBeInTheDocument();
        expect(screen.queryByRole("option", { name: "CVT" })).not.toBeInTheDocument();
    });

    it("closes the make dropdown when the x button is clicked", async () => {
        const user = userEvent.setup();
        setFakeSupabase(makeFakeSupabase());
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        expect(screen.getByRole("checkbox", { name: "Toyota" })).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Close Make" }));

        expect(screen.queryByRole("checkbox", { name: "Toyota" })).not.toBeInTheDocument();
    });

    it("matches any of several selected makes and models (AND across fields, OR within each)", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({
            listingsResult: {
                data: [
                    makeListing(),
                    makeListing({ id: "listing-2", make: "Lexus", model: "ES" }),
                    makeListing({ id: "listing-3", make: "Honda", model: "Civic" }),
                ],
                error: null,
            },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));
        await user.click(screen.getByRole("checkbox", { name: "Lexus" }));

        await waitFor(() => {
            expect(fake.listingsQuery.or).toHaveBeenCalledWith("make.ilike.Toyota,make.ilike.Lexus");
        });
    });

    it("lets the customer type into the make dropdown to filter the checkbox list", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({
            listingsResult: {
                data: [
                    makeListing(),
                    makeListing({ id: "listing-2", make: "Lexus", model: "ES" }),
                    makeListing({ id: "listing-3", make: "Honda", model: "Civic" }),
                ],
                error: null,
            },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        expect(screen.getByRole("checkbox", { name: "Toyota" })).toBeInTheDocument();
        expect(screen.getByRole("checkbox", { name: "Honda" })).toBeInTheDocument();

        await user.type(screen.getByRole("textbox", { name: "Search Make" }), "lex");

        expect(screen.getByRole("checkbox", { name: "Lexus" })).toBeInTheDocument();
        expect(screen.queryByRole("checkbox", { name: "Toyota" })).not.toBeInTheDocument();
        expect(screen.queryByRole("checkbox", { name: "Honda" })).not.toBeInTheDocument();
    });

    it("only offers models belonging to the selected make(s)", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({
            listingsResult: {
                data: [
                    makeListing(), // Toyota Camry
                    makeListing({ id: "listing-2", make: "Lexus", model: "ES" }),
                    makeListing({ id: "listing-3", make: "Honda", model: "Civic" }),
                ],
                error: null,
            },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        // Before picking a make, every model is available.
        await user.click(screen.getByLabelText("Model"));
        expect(screen.getByRole("checkbox", { name: "Camry" })).toBeInTheDocument();
        expect(screen.getByRole("checkbox", { name: "Civic" })).toBeInTheDocument();
        expect(screen.getByRole("checkbox", { name: "ES" })).toBeInTheDocument();
        await user.click(screen.getByLabelText("Model")); // close

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));

        await user.click(screen.getByLabelText("Model"));
        expect(screen.getByRole("checkbox", { name: "Camry" })).toBeInTheDocument();
        expect(screen.queryByRole("checkbox", { name: "Civic" })).not.toBeInTheDocument();
        expect(screen.queryByRole("checkbox", { name: "ES" })).not.toBeInTheDocument();
    });

    it("drops a selected model that's no longer valid after the make selection narrows", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({
            listingsResult: {
                data: [
                    makeListing(), // Toyota Camry
                    makeListing({ id: "listing-2", make: "Honda", model: "Civic" }),
                ],
                error: null,
            },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Model"));
        await user.click(screen.getByRole("checkbox", { name: "Civic" }));
        expect(screen.getByLabelText("Model")).toHaveTextContent("Civic");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));

        await waitFor(() => {
            expect(screen.getByLabelText("Model")).toHaveTextContent("All Models");
        });
    });

    it("moving the sliders updates the displayed value and re-queries with the new bound", async () => {
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        const minYearSlider = screen.getByRole("slider", { name: /Min Year/ });
        fireEvent.change(minYearSlider, { target: { value: "2019" } });

        expect(await screen.findByText("2019")).toBeInTheDocument();
        await waitFor(() => {
            expect(fake.listingsQuery.gte).toHaveBeenCalledWith("model_year", 2019);
        });
    });

    it("clicking clear filters resets the make selection back to 'All Makes'", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: { data: [], error: null },
                filterOptionsResult: { data: [makeListing()], error: null },
            })
        );
        render(<Home />);
        await screen.findByText("No vehicles found matching your criteria.");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));
        expect(screen.getByLabelText("Make")).toHaveTextContent("Toyota");

        await user.click(screen.getByRole("button", { name: "Clear filters and try again" }));

        expect(screen.getByLabelText("Make")).toHaveTextContent("All Makes");
    });
});

describe("listing display", () => {
    it("shows the dealership name and city instead of the raw platform code", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: {
                    data: [makeListing({ marketplace_source: "dealerinspire", dealer_name: "Capitol Honda", city: "San Jose" })],
                    error: null,
                },
            })
        );

        render(<Home />);

        expect(await screen.findByText("Capitol Honda · San Jose")).toBeInTheDocument();
        expect(screen.queryByText("dealerinspire")).not.toBeInTheDocument();
    });

    it("shows just the dealership name when no city is known", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: {
                    data: [makeListing({ marketplace_source: "dealeron", dealer_name: "Stevens Creek Toyota", city: null })],
                    error: null,
                },
            })
        );

        render(<Home />);

        expect(await screen.findByText("Stevens Creek Toyota")).toBeInTheDocument();
    });

    it("falls back to a friendly marketplace label when there's no dealer name", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: {
                    data: [makeListing({ marketplace_source: "craigslist", dealer_name: null })],
                    error: null,
                },
            })
        );

        render(<Home />);

        expect(await screen.findByText("Craigslist")).toBeInTheDocument();
    });

    it("shows a Good Deal badge with the discount percentage when is_good_deal is true", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: {
                    data: [makeListing({ is_good_deal: true, deal_score: 0.183 })],
                    error: null,
                },
            })
        );

        render(<Home />);

        expect(await screen.findByText("🔥 Good Deal · 18% off")).toBeInTheDocument();
    });

    it("does not show a Good Deal badge when is_good_deal is false", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: { data: [makeListing({ is_good_deal: false })], error: null },
            })
        );

        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByText(/Good Deal/)).not.toBeInTheDocument();
    });

    it("shows how long ago the listing was last confirmed by the scraper", async () => {
        const twoHoursAgo = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: { data: [makeListing({ last_seen_at: twoHoursAgo })], error: null },
            })
        );

        render(<Home />);

        expect(await screen.findByText("Updated 2 hours ago")).toBeInTheDocument();
    });

    it("shows nothing for last-updated when last_seen_at is missing", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: { data: [makeListing({ last_seen_at: null })], error: null },
            })
        );

        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByText(/Updated/)).not.toBeInTheDocument();
    });
});

describe("sorting", () => {
    it("defaults to sorting by best deal", async () => {
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(fake.listingsQuery.order).toHaveBeenCalledWith("deal_score", {
            ascending: false,
            nullsFirst: false,
        });
        // last_seen_at is always the tiebreaker, regardless of primary sort.
        expect(fake.listingsQuery.order).toHaveBeenCalledWith("last_seen_at", {
            ascending: false,
            nullsFirst: false,
        });
        expect(screen.getByRole("combobox", { name: "Sort by" })).toHaveValue("best_deal");
    });

    it("re-queries with the new sort order when the customer changes it", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.selectOptions(screen.getByRole("combobox", { name: "Sort by" }), "price_asc");

        await waitFor(() => {
            expect(fake.listingsQuery.order).toHaveBeenCalledWith("price", {
                ascending: true,
                nullsFirst: false,
            });
        });
    });
});

describe("pagination", () => {
    it("does not show Load More when fewer than a full page of results comes back", async () => {
        setFakeSupabase(makeFakeSupabase({ listingsResult: { data: [makeListing()], error: null } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByRole("button", { name: "Load More" })).not.toBeInTheDocument();
    });

    it("shows Load More when a full page of results comes back", async () => {
        setFakeSupabase(
            makeFakeSupabase({ listingsResult: { data: makeListings(50, "page1"), error: null } })
        );
        render(<Home />);

        expect(await screen.findByRole("button", { name: "Load More" })).toBeInTheDocument();
    });

    it("clicking Load More appends the next page instead of replacing the current results", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({
            listingsResult: { data: makeListings(50, "page1"), error: null },
            loadMoreResult: { data: makeListings(3, "page2"), error: null },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByRole("button", { name: "Load More" });

        await user.click(screen.getByRole("button", { name: "Load More" }));

        await waitFor(() => {
            expect(fake.listingsQuery.range).toHaveBeenCalledWith(50, 99);
        });
        // First page's cars are still there, plus the newly appended ones.
        expect(screen.getByText("2022 Toyota Camry-page1-0")).toBeInTheDocument();
        expect(await screen.findByText("2022 Toyota Camry-page2-0")).toBeInTheDocument();
    });

    it("hides Load More once the appended page comes back under a full page", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
                listingsResult: { data: makeListings(50, "page1"), error: null },
                loadMoreResult: { data: makeListings(3, "page2"), error: null },
            })
        );
        render(<Home />);
        await screen.findByRole("button", { name: "Load More" });

        await user.click(screen.getByRole("button", { name: "Load More" }));

        await waitFor(() => {
            expect(screen.queryByRole("button", { name: "Load More" })).not.toBeInTheDocument();
        });
    });
});

describe("auth", () => {
    it("shows a login form and hides Save Search when logged out", async () => {
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.getByPlaceholderText("Email address")).toBeInTheDocument();
        expect(screen.getByPlaceholderText("Password")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Save Search" })).not.toBeInTheDocument();
    });

    it("logging in with valid credentials switches to the Save Search form", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByPlaceholderText("Email address"), "owner@example.com");
        await user.type(screen.getByPlaceholderText("Password"), "hunter22");
        await user.click(screen.getByRole("button", { name: "Log In" }));

        expect(fake.auth.signInWithPassword).toHaveBeenCalledWith({
            email: "owner@example.com",
            password: "hunter22",
        });
        expect(await screen.findByText(/Signed in as/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Save Search" })).toBeInTheDocument();
    });

    it("shows an error message when login fails", async () => {
        const user = userEvent.setup();
        setFakeSupabase(makeFakeSupabase({ signInResult: { error: { message: "Invalid credentials" } } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByPlaceholderText("Email address"), "owner@example.com");
        await user.type(screen.getByPlaceholderText("Password"), "wrongpass");
        await user.click(screen.getByRole("button", { name: "Log In" }));

        expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Save Search" })).not.toBeInTheDocument();
    });

    it("toggling to sign-up mode and submitting calls signUp instead", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByRole("button", { name: "Sign up" }));
        await user.type(screen.getByPlaceholderText("Email address"), "new@example.com");
        await user.type(screen.getByPlaceholderText("Password"), "hunter22");
        await user.click(screen.getByRole("button", { name: "Sign Up" }));

        expect(fake.auth.signUp).toHaveBeenCalledWith({ email: "new@example.com", password: "hunter22" });
        expect(fake.auth.signInWithPassword).not.toHaveBeenCalled();
    });

    it("logging out returns to the login form", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({ authUser: LOGGED_IN_USER });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText(/Signed in as/);

        await user.click(screen.getByRole("button", { name: "Log out" }));

        expect(fake.auth.signOut).toHaveBeenCalled();
        expect(await screen.findByPlaceholderText("Email address")).toBeInTheDocument();
    });

    it("prefills the digest email from the logged-in account", async () => {
        setFakeSupabase(makeFakeSupabase({ authUser: LOGGED_IN_USER_WITH_EMAIL }));
        render(<Home />);
        await screen.findByText(/Signed in as/);

        // The prefill runs in a separate effect cycle right after "user"
        // is set, one render after the "Signed in as" text commits.
        await waitFor(() => {
            expect(screen.getByPlaceholderText("Enter your email")).toHaveValue("owner@example.com");
        });
    });
});

describe("save search", () => {
    it("warns instead of saving when no email is entered", async () => {
        const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
        const user = userEvent.setup();
        const fake = makeFakeSupabase({ authUser: LOGGED_IN_USER });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(alertSpy).toHaveBeenCalledWith("Please enter an email address first.");
        expect(fake.savedSearchesTable.insert).not.toHaveBeenCalled();
        alertSpy.mockRestore();
    });

    it("asks for confirmation before saving a search with no filters, and respects Cancel", async () => {
        const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
        const user = userEvent.setup();
        const fake = makeFakeSupabase({ authUser: LOGGED_IN_USER });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(confirmSpy).toHaveBeenCalled();
        expect(fake.savedSearchesTable.insert).not.toHaveBeenCalled();
        confirmSpy.mockRestore();
    });

    it("saves a no-filter search when the customer confirms the warning", async () => {
        const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
        const user = userEvent.setup();
        const fake = makeFakeSupabase({ authUser: LOGGED_IN_USER });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        await waitFor(() => expect(fake.savedSearchesTable.insert).toHaveBeenCalled());
        const payload = fake.savedSearchesTable.insert.mock.calls[0][0];
        expect(payload.email).toBe("buyer@example.com");
        expect(payload.min_year).toBeNull();
        expect(payload.max_mileage).toBeNull();
        expect(payload.max_price).toBeNull();
        confirmSpy.mockRestore();
    });

    it("saves immediately without confirmation when a real filter is set", async () => {
        const confirmSpy = vi.spyOn(window, "confirm");
        const user = userEvent.setup();
        const fake = makeFakeSupabase({ authUser: LOGGED_IN_USER });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));
        await user.type(screen.getByPlaceholderText("Name this search (e.g. Lexus ES)"), "Toyota watch");
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(confirmSpy).not.toHaveBeenCalled();
        await waitFor(() => expect(fake.savedSearchesTable.insert).toHaveBeenCalled());
        const payload = fake.savedSearchesTable.insert.mock.calls[0][0];
        expect(payload).toMatchObject({
            make: ["Toyota"],
            name: "Toyota watch",
            email: "buyer@example.com",
            notification_grouping: "combined",
        });
        confirmSpy.mockRestore();
    });

    it("includes the chosen notification_grouping in the saved-search payload", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({ authUser: LOGGED_IN_USER });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("radio", { name: "make" }));
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        await waitFor(() => expect(fake.savedSearchesTable.insert).toHaveBeenCalled());
        const payload = fake.savedSearchesTable.insert.mock.calls[0][0];
        expect(payload.notification_grouping).toBe("make");
    });

    it("shows a Saved! confirmation after a successful save", async () => {
        const user = userEvent.setup();
        setFakeSupabase(makeFakeSupabase({ authUser: LOGGED_IN_USER, insertResult: { error: null } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(await screen.findByRole("button", { name: "Saved!" })).toBeInTheDocument();
    });

    it("shows an Error state when the save fails", async () => {
        const user = userEvent.setup();
        setFakeSupabase(makeFakeSupabase({ authUser: LOGGED_IN_USER, insertResult: { error: { message: "boom" } } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(await screen.findByRole("button", { name: "Error" })).toBeInTheDocument();
    });
});

describe("my saved searches", () => {
    it("shows nothing when logged out", async () => {
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByText("My Saved Searches")).not.toBeInTheDocument();
    });

    it("lists this account's saved searches fetched from Supabase", async () => {
        const fake = makeFakeSupabase({
            authUser: LOGGED_IN_USER,
            savedSearchesSelectResult: {
                data: [
                    {
                        id: "search-1",
                        name: "Lexus ES",
                        make: ["Lexus"],
                        model: ["ES"],
                        min_year: 2018,
                        max_mileage: 60000,
                        max_price: 30000,
                        email: "buyer@example.com",
                    },
                ],
                error: null,
            },
        });
        setFakeSupabase(fake);

        render(<Home />);

        expect(await screen.findByText("Lexus ES")).toBeInTheDocument();
        expect(screen.getByText(/Lexus ES — 2018\+, under 60,000 mi, under \$30,000/)).toBeInTheDocument();
        expect(fake.savedSearchesTable.select).toHaveBeenCalled();
    });

    it("collapses and re-expands the saved searches list", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                savedSearchesSelectResult: {
                    data: [{ id: "search-1", name: "Lexus ES", email: "buyer@example.com" }],
                    error: null,
                },
            })
        );
        render(<Home />);
        await screen.findByText("Lexus ES");

        await user.click(screen.getByRole("button", { name: /My Saved Searches/ }));
        expect(screen.queryByText("Lexus ES")).not.toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: /My Saved Searches/ }));
        expect(await screen.findByText("Lexus ES")).toBeInTheDocument();
    });

    it("appends the new search to the list after a successful save", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                insertResult: {
                    data: { id: "new-search", name: "Toyota watch", make: ["Toyota"], email: "buyer@example.com" },
                    error: null,
                },
            })
        );
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByLabelText("Make"));
        await user.click(screen.getByRole("checkbox", { name: "Toyota" }));
        await user.type(screen.getByPlaceholderText("Name this search (e.g. Lexus ES)"), "Toyota watch");
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(await screen.findByText("Toyota watch")).toBeInTheDocument();
    });

    it("shows multiple makes/models joined together, with a grouping annotation when set", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                savedSearchesSelectResult: {
                    data: [
                        {
                            id: "search-2",
                            name: "Toyota or Lexus",
                            make: ["Toyota", "Lexus"],
                            model: null,
                            email: "buyer@example.com",
                            notification_grouping: "make",
                        },
                    ],
                    error: null,
                },
            })
        );

        render(<Home />);

        expect(await screen.findByText("Toyota or Lexus")).toBeInTheDocument();
        expect(screen.getByText(/Toyota, Lexus \(grouped by make\)/)).toBeInTheDocument();
    });

    it("deletes a saved search from Supabase and removes it from the list", async () => {
        const onDelete = vi.fn();
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                savedSearchesSelectResult: {
                    data: [{ id: "search-1", name: "Lexus ES", email: "buyer@example.com" }],
                    error: null,
                },
                onDelete,
            })
        );
        const user = userEvent.setup();
        render(<Home />);
        await screen.findByText("Lexus ES");

        await user.click(screen.getByRole("button", { name: "Delete Lexus ES" }));

        await waitFor(() => expect(onDelete).toHaveBeenCalledWith("search-1"));
        expect(screen.queryByText("Lexus ES")).not.toBeInTheDocument();
    });

    it("clicking Edit loads the search's filters into the main form and submits an update", async () => {
        const user = userEvent.setup();
        const onUpdate = vi.fn();
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                savedSearchesSelectResult: {
                    data: [
                        {
                            id: "search-1",
                            name: "Lexus ES",
                            email: "buyer@example.com",
                            make: ["Lexus"],
                            model: ["ES"],
                            notification_grouping: "combined",
                        },
                    ],
                    error: null,
                },
                updateResult: { data: { id: "search-1", name: "Lexus ES Updated" }, error: null },
                onUpdate,
            })
        );
        render(<Home />);
        await screen.findByText("Lexus ES");

        await user.click(screen.getByRole("button", { name: "Edit Lexus ES" }));

        expect(screen.getByPlaceholderText("Name this search (e.g. Lexus ES)")).toHaveValue("Lexus ES");
        expect(screen.getByPlaceholderText("Enter your email")).toHaveValue("buyer@example.com");
        expect(screen.getByRole("button", { name: "Update Search" })).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Update Search" }));

        await waitFor(() => expect(onUpdate).toHaveBeenCalledWith("search-1", expect.objectContaining({ name: "Lexus ES" })));
        expect(await screen.findByText("Lexus ES Updated")).toBeInTheDocument();
    });

    it("clicking Cancel while editing clears the form and returns to Save Search", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                savedSearchesSelectResult: {
                    data: [{ id: "search-1", name: "Lexus ES", email: "buyer@example.com" }],
                    error: null,
                },
            })
        );
        render(<Home />);
        await screen.findByText("Lexus ES");

        await user.click(screen.getByRole("button", { name: "Edit Lexus ES" }));
        expect(screen.getByRole("button", { name: "Update Search" })).toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: "Cancel" }));

        expect(screen.getByRole("button", { name: "Save Search" })).toBeInTheDocument();
        expect(screen.getByPlaceholderText("Name this search (e.g. Lexus ES)")).toHaveValue("");
    });

    it("pausing a saved search updates is_active and shows a Paused label", async () => {
        const user = userEvent.setup();
        const onUpdate = vi.fn();
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                savedSearchesSelectResult: {
                    data: [{ id: "search-1", name: "Lexus ES", email: "buyer@example.com", is_active: true }],
                    error: null,
                },
                onUpdate,
            })
        );
        render(<Home />);
        await screen.findByText("Lexus ES");

        await user.click(screen.getByRole("button", { name: "Pause Lexus ES" }));

        await waitFor(() => expect(onUpdate).toHaveBeenCalledWith("search-1", { is_active: false }));
        expect(await screen.findByText("(Paused)")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Resume Lexus ES" })).toBeInTheDocument();
    });
});

describe("favorites", () => {
    it("hides the favorite button when logged out", async () => {
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByLabelText(/favorites/)).not.toBeInTheDocument();
    });

    it("shows an outlined heart for a listing that isn't favorited yet", async () => {
        setFakeSupabase(makeFakeSupabase({ authUser: LOGGED_IN_USER }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(
            screen.getByRole("button", { name: "Add 2022 Toyota Camry to favorites" })
        ).toBeInTheDocument();
    });

    it("favoriting a listing calls insert and flips the icon to filled", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase({ authUser: LOGGED_IN_USER });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.click(screen.getByRole("button", { name: "Add 2022 Toyota Camry to favorites" }));

        expect(fake.favoritesTable.insert).toHaveBeenCalledWith({
            user_id: "user-1",
            listing_id: "listing-1",
        });
        // Now favorited, so it renders both in the main grid and the new
        // "My Favorites" section -- two matching buttons is correct here.
        expect(
            await screen.findAllByRole("button", { name: "Remove 2022 Toyota Camry from favorites" })
        ).toHaveLength(2);
    });

    it("unfavoriting a listing calls delete with the right user and listing", async () => {
        const user = userEvent.setup();
        const onFavoriteDelete = vi.fn();
        const fake = makeFakeSupabase({
            authUser: LOGGED_IN_USER,
            favoritesSelectResult: { data: [{ listings: makeListing() }], error: null },
            onFavoriteDelete,
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findAllByRole("button", { name: "Remove 2022 Toyota Camry from favorites" });

        await user.click(screen.getAllByRole("button", { name: "Remove 2022 Toyota Camry from favorites" })[0]);

        await waitFor(() => expect(onFavoriteDelete).toHaveBeenCalledWith("user-1", "listing-1"));
    });

    it("shows a My Favorites section listing favorited cars, hidden when empty", async () => {
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                favoritesSelectResult: {
                    data: [{ listings: makeListing({ id: "listing-2", make: "Honda", model: "Civic" }) }],
                    error: null,
                },
            })
        );
        render(<Home />);

        expect(await screen.findByText(/My Favorites/)).toBeInTheDocument();
        expect(screen.getByText("2022 Honda Civic")).toBeInTheDocument();
    });

    it("collapses and re-expands the My Favorites section", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                favoritesSelectResult: {
                    data: [{ listings: makeListing({ id: "listing-2", make: "Honda", model: "Civic" }) }],
                    error: null,
                },
            })
        );
        render(<Home />);
        await screen.findByText("2022 Honda Civic");

        await user.click(screen.getByRole("button", { name: /My Favorites/ }));
        expect(screen.queryByText("2022 Honda Civic")).not.toBeInTheDocument();

        await user.click(screen.getByRole("button", { name: /My Favorites/ }));
        expect(await screen.findByText("2022 Honda Civic")).toBeInTheDocument();
    });

    it("does not show a My Favorites section when there are none", async () => {
        setFakeSupabase(makeFakeSupabase({ authUser: LOGGED_IN_USER }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByText("My Favorites")).not.toBeInTheDocument();
    });
});

describe("radius search", () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    async function openLocationFilter(user: ReturnType<typeof userEvent.setup>) {
        await user.click(screen.getByRole("button", { name: /Location/ }));
    }

    it("resolves a valid zip and queries nearby_listings with the chosen radius", async () => {
        const user = userEvent.setup();
        vi.stubGlobal(
            "fetch",
            vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ lat: 37.3541, lng: -121.9552 }) }))
        );
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await openLocationFilter(user);
        await user.type(screen.getByLabelText("Zip Code"), "95050");
        await user.selectOptions(screen.getByLabelText("Search Radius"), "50");
        await user.click(screen.getByRole("button", { name: "Search" }));

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledWith("/api/geocode-zip?zip=95050");
        });
        await waitFor(() => {
            expect(fake.rpc).toHaveBeenCalledWith("nearby_listings", {
                center_lat: 37.3541,
                center_lng: -121.9552,
                radius_miles: 50,
            });
        });
    });

    it("shows an inline error and never hits the network for a malformed zip", async () => {
        const user = userEvent.setup();
        const fetchSpy = vi.fn();
        vi.stubGlobal("fetch", fetchSpy);
        setFakeSupabase(makeFakeSupabase());
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await openLocationFilter(user);
        await user.type(screen.getByLabelText("Zip Code"), "abc");
        await user.click(screen.getByRole("button", { name: "Search" }));

        expect(await screen.findByText("Enter a 5-digit US zip code.")).toBeInTheDocument();
        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("shows the server's error and does not call nearby_listings when the zip can't be resolved", async () => {
        const user = userEvent.setup();
        vi.stubGlobal(
            "fetch",
            vi.fn(() =>
                Promise.resolve({ ok: false, json: () => Promise.resolve({ error: "Couldn't find zip code 00000." }) })
            )
        );
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await openLocationFilter(user);
        await user.type(screen.getByLabelText("Zip Code"), "00000");
        await user.click(screen.getByRole("button", { name: "Search" }));

        expect(await screen.findByText("Couldn't find zip code 00000.")).toBeInTheDocument();
        expect(fake.rpc).not.toHaveBeenCalled();
    });

    it("reuses the resolved coordinates on Load More instead of re-resolving the zip", async () => {
        const user = userEvent.setup();
        const fetchSpy = vi.fn(() =>
            Promise.resolve({ ok: true, json: () => Promise.resolve({ lat: 37.3541, lng: -121.9552 }) })
        );
        vi.stubGlobal("fetch", fetchSpy);
        const fake = makeFakeSupabase({
            listingsResult: { data: makeListings(50, "page1"), error: null },
            loadMoreResult: { data: makeListings(3, "page2"), error: null },
        });
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByRole("button", { name: "Load More" });

        await openLocationFilter(user);
        await user.type(screen.getByLabelText("Zip Code"), "95050");
        await user.click(screen.getByRole("button", { name: "Search" }));
        await waitFor(() => expect(fake.rpc).toHaveBeenCalled());

        await user.click(screen.getByRole("button", { name: "Load More" }));

        await waitFor(() => {
            expect(fake.listingsQuery.range).toHaveBeenCalledWith(50, 99);
        });
        expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    it("falls back to the plain listings query after the zip filter is cleared", async () => {
        const user = userEvent.setup();
        vi.stubGlobal(
            "fetch",
            vi.fn(() => Promise.resolve({ ok: true, json: () => Promise.resolve({ lat: 37.3541, lng: -121.9552 }) }))
        );
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await openLocationFilter(user);
        const zipInput = screen.getByLabelText("Zip Code");
        await user.type(zipInput, "95050");
        await user.click(screen.getByRole("button", { name: "Search" }));
        await waitFor(() => expect(fake.rpc).toHaveBeenCalledTimes(1));

        await user.clear(zipInput);
        await user.click(screen.getByRole("button", { name: "Search" }));

        // No new rpc call once the filter is cleared -- the query falls
        // back to the plain .from("listings") path.
        await waitFor(() => expect(fake.from).toHaveBeenCalledWith("listings"));
        expect(fake.rpc).toHaveBeenCalledTimes(1);
    });
});
