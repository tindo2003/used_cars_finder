import type { NextConfig } from "next";

const nextConfig = {
    images: {
        remotePatterns: [
            {
                protocol: "https",
                hostname: "**", // Allows images from ANY domain
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
