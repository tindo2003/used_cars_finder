import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
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

type SavedSearchPayload = {
    name: string | null;
    email: string;
    make: string | null;
    model: string | null;
    min_year: number | null;
    max_mileage: number | null;
    max_price: number | null;
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
    insertResult = { data: { id: "search-1" }, error: null },
    savedSearchesSelectResult = { data: [], error: null },
    deleteResult = { error: null },
    authUser = null as { id: string; email: string } | null,
    signInResult = { error: null as { message: string } | null },
    signUpResult = { error: null as { message: string } | null },
    onInsert,
    onDelete,
}: {
    listingsResult?: { data: unknown[]; error: unknown };
    insertResult?: { data?: unknown; error: unknown };
    savedSearchesSelectResult?: { data: unknown[]; error: unknown };
    deleteResult?: { error: unknown };
    authUser?: { id: string; email: string } | null;
    signInResult?: { error: { message: string } | null };
    signUpResult?: { error: { message: string } | null };
    onInsert?: (payload: SavedSearchPayload) => void;
    onDelete?: (id: unknown) => void;
} = {}) {
    function makeChainable(result: unknown, methods: string[]) {
        const chain: any = {};
        for (const method of methods) {
            chain[method] = vi.fn(() => chain);
        }
        chain.then = (resolve: (value: unknown) => void) => resolve(result);
        return chain;
    }

    const listingsQuery = makeChainable(listingsResult, [
        "select",
        "eq",
        "is",
        "order",
        "ilike",
        "gte",
        "lte",
        "limit",
    ]);

    const savedSearchesTable = {
        insert: vi.fn((payload: SavedSearchPayload) => {
            onInsert?.(payload);
            return makeChainable(insertResult, ["select", "single"]);
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

    const from = vi.fn((table: string) => {
        if (table === "listings") return listingsQuery;
        if (table === "saved_searches") return savedSearchesTable;
        throw new Error(`Unexpected table: ${table}`);
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

    return { from, auth, listingsQuery, savedSearchesTable };
}

beforeEach(() => {
    setFakeSupabase(makeFakeSupabase());
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

    it("lets the customer type a make and model and submit the search", async () => {
        const user = userEvent.setup();
        const fake = makeFakeSupabase();
        setFakeSupabase(fake);
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByLabelText("Make"), "Lexus");
        await user.type(screen.getByLabelText("Model"), "ES");
        await user.click(screen.getByRole("button", { name: "Search" }));

        await waitFor(() => {
            expect(fake.listingsQuery.ilike).toHaveBeenCalledWith("make", "%Lexus%");
            expect(fake.listingsQuery.ilike).toHaveBeenCalledWith("model", "%ES%");
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

    it("clicking clear filters resets make/model back to empty", async () => {
        const user = userEvent.setup();
        setFakeSupabase(makeFakeSupabase({ listingsResult: { data: [], error: null } }));
        render(<Home />);
        await screen.findByText("No vehicles found matching your criteria.");

        await user.type(screen.getByLabelText("Make"), "Honda");
        await user.click(screen.getByRole("button", { name: "Clear filters and try again" }));

        expect(screen.getByLabelText("Make")).toHaveValue("");
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

        await user.type(screen.getByLabelText("Make"), "Honda");
        await user.type(screen.getByPlaceholderText("Name this search (e.g. Lexus ES)"), "Honda watch");
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(confirmSpy).not.toHaveBeenCalled();
        await waitFor(() => expect(fake.savedSearchesTable.insert).toHaveBeenCalled());
        const payload = fake.savedSearchesTable.insert.mock.calls[0][0];
        expect(payload).toMatchObject({ make: "Honda", name: "Honda watch", email: "buyer@example.com" });
        confirmSpy.mockRestore();
    });

    it("shows a Saved! confirmation after a successful save", async () => {
        const user = userEvent.setup();
        setFakeSupabase(makeFakeSupabase({ authUser: LOGGED_IN_USER, insertResult: { error: null } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByLabelText("Make"), "Honda");
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(await screen.findByRole("button", { name: "Saved!" })).toBeInTheDocument();
    });

    it("shows an Error state when the save fails", async () => {
        const user = userEvent.setup();
        setFakeSupabase(makeFakeSupabase({ authUser: LOGGED_IN_USER, insertResult: { error: { message: "boom" } } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByLabelText("Make"), "Honda");
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
                        make: "Lexus",
                        model: "ES",
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

    it("appends the new search to the list after a successful save", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
                authUser: LOGGED_IN_USER,
                insertResult: {
                    data: { id: "new-search", name: "Honda watch", make: "Honda", email: "buyer@example.com" },
                    error: null,
                },
            })
        );
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByLabelText("Make"), "Honda");
        await user.type(screen.getByPlaceholderText("Name this search (e.g. Lexus ES)"), "Honda watch");
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(await screen.findByText("Honda watch")).toBeInTheDocument();
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
});
