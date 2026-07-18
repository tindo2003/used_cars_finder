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
    insertResult = { error: null },
    onInsert,
}: {
    listingsResult?: { data: unknown[]; error: unknown };
    insertResult?: { error: unknown };
    onInsert?: (payload: SavedSearchPayload) => void;
} = {}) {
    const listingsQuery: any = {};
    for (const method of ["select", "eq", "order", "ilike", "gte", "lte", "limit"]) {
        listingsQuery[method] = vi.fn(() => listingsQuery);
    }
    listingsQuery.then = (resolve: (value: unknown) => void) => resolve(listingsResult);

    const savedSearchesTable = {
        insert: vi.fn((payload: SavedSearchPayload) => {
            onInsert?.(payload);
            return Promise.resolve(insertResult);
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
