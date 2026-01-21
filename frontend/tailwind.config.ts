import type { Config } from "tailwindcss";

const config: Config = {
    content: [
        "./app/**/*.{js,ts,jsx,tsx,mdx}",
        "./components/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                primary: "var(--primary-color)",
                secondary: "var(--secondary-color)",
                accent: "var(--accent-color)",
                background: "var(--bg-dark)",
                sidebar: "var(--bg-sidebar)",
            },
        },
    },
    plugins: [],
};
export default config;
