import type { NextConfig } from "next";

const nextConfig = {
    images: {
        // Disabled: these are hotlinked third-party dealer/marketplace
        // photos we don't control, so there's little real benefit to
        // Next's resize/format optimization here, and remotePatterns is
        // already wide open ("**") so it's not narrowing any security
        // surface either. More importantly, Next's image-proxy has an
        // SSRF guard that refuses to fetch an upstream image if its
        // hostname resolves to what it flags as a "private" IP -- this
        // false-positives on NAT64/DNS64 IPv6-only networks (confirmed
        // live: `64:ff9b::...` synthetic addresses), which also affects
        // real users on IPv6-only mobile carriers, not just this dev
        // sandbox. Bypassing the proxy entirely sidesteps that whole
        // class of failure; the image still loads fine directly.
        unoptimized: true,
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
