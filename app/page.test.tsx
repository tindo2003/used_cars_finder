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

function makeFakeSupabase({
    listingsResult = { data: [makeListing()], error: null },
    insertResult = { data: { id: "search-1" }, error: null },
    savedSearchesSelectResult = { data: [], error: null },
    deleteResult = { error: null },
    onInsert,
    onDelete,
}: {
    listingsResult?: { data: unknown[]; error: unknown };
    insertResult?: { data?: unknown; error: unknown };
    savedSearchesSelectResult?: { data: unknown[]; error: unknown };
    deleteResult?: { error: unknown };
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

    return { from, listingsQuery, savedSearchesTable };
}

beforeEach(() => {
    window.localStorage.clear();
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

describe("save search", () => {
    it("warns instead of saving when no email is entered", async () => {
        const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
        const user = userEvent.setup();
        const fake = makeFakeSupabase();
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
        const fake = makeFakeSupabase();
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
        const fake = makeFakeSupabase();
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
        const fake = makeFakeSupabase();
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
        setFakeSupabase(makeFakeSupabase({ insertResult: { error: null } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByLabelText("Make"), "Honda");
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(await screen.findByRole("button", { name: "Saved!" })).toBeInTheDocument();
    });

    it("shows an Error state when the save fails", async () => {
        const user = userEvent.setup();
        setFakeSupabase(makeFakeSupabase({ insertResult: { error: { message: "boom" } } }));
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        await user.type(screen.getByLabelText("Make"), "Honda");
        await user.type(screen.getByPlaceholderText("Enter your email"), "buyer@example.com");
        await user.click(screen.getByRole("button", { name: "Save Search" }));

        expect(await screen.findByRole("button", { name: "Error" })).toBeInTheDocument();
    });
});

describe("my saved searches", () => {
    it("shows nothing when this browser hasn't saved any searches", async () => {
        render(<Home />);
        await screen.findByText("2022 Toyota Camry");

        expect(screen.queryByText("My Saved Searches")).not.toBeInTheDocument();
    });

    it("lists a saved search fetched from Supabase for an id already in localStorage", async () => {
        window.localStorage.setItem("savedSearchIds", JSON.stringify(["search-1"]));
        setFakeSupabase(
            makeFakeSupabase({
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
            })
        );

        render(<Home />);

        expect(await screen.findByText("Lexus ES")).toBeInTheDocument();
        expect(screen.getByText(/Lexus ES — 2018\+, under 60,000 mi, under \$30,000/)).toBeInTheDocument();
    });

    it("appends the new search to the list after a successful save", async () => {
        const user = userEvent.setup();
        setFakeSupabase(
            makeFakeSupabase({
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
        expect(JSON.parse(window.localStorage.getItem("savedSearchIds") || "[]")).toEqual(["new-search"]);
    });

    it("deletes a saved search from Supabase and removes it from the list", async () => {
        window.localStorage.setItem("savedSearchIds", JSON.stringify(["search-1"]));
        const onDelete = vi.fn();
        setFakeSupabase(
            makeFakeSupabase({
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
        expect(JSON.parse(window.localStorage.getItem("savedSearchIds") || "[]")).toEqual([]);
    });
});
