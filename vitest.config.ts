import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";

export default defineConfig({
    // Type-only clash between vitest's bundled vite and @vitejs/plugin-react's
    // peer vite version; both work fine together at runtime.
    plugins: [tsconfigPaths(), react()] as any,
    test: {
        environment: "jsdom",
        setupFiles: ["./vitest.setup.ts"],
        globals: true,
    },
});
