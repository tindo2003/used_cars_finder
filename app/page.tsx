import { createClient } from "@/utils/supabase/server";
import { cookies } from "next/headers";

export default async function Page() {
    const cookieStore = await cookies();
    const supabase = createClient(cookieStore);

    // Fetch active car listings instead of todos
    const { data: listings, error } = await supabase
        .from("listings")
        .select("*")
        .eq("status", "active")
        .order("posted_at", { ascending: false })
        .limit(20);

    if (error) {
        return (
            <div className="p-8 text-red-500">
                Error loading cars: {error.message}
            </div>
        );
    }

    return (
        <main className="p-8 max-w-4xl mx-auto">
            <h1 className="text-2xl font-bold mb-6">Used Car Finder</h1>

            {listings?.length === 0 ? (
                <p>No cars found. Your database is empty!</p>
            ) : (
                <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {listings?.map((car) => (
                        <li key={car.id} className="border p-4 rounded shadow">
                            <h2 className="text-xl font-semibold">
                                {car.model_year} {car.make} {car.model}
                            </h2>
                            <p className="text-green-600 font-bold">
                                ${car.price.toLocaleString()}
                            </p>
                            <p className="text-sm text-gray-500 mt-2">
                                Found on {car.marketplace_source}
                            </p>
                        </li>
                    ))}
                </ul>
            )}
        </main>
    );
}
