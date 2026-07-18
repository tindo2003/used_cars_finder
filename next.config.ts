import type { NextConfig } from "next";

const nextConfig = {
    images: {
        remotePatterns: [
            {
                protocol: "https", // Or 'http' if the site isn't SSL
                hostname: "www.stevenscreektoyota.com", // Use the actual domain of the dealer
                pathname: "/inventoryphotos/**",
            },
        ],
        // If you prefer to handle the path locally as you were trying:
        localPatterns: [
            {
                pathname: "/inventoryphotos/**",
                search: "",
            },
        ],
    },
};

export default nextConfig;
