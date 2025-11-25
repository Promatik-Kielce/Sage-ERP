/** @odoo-module **/

import { registry } from "@web/core/registry";
import { browser } from "@web/core/browser/browser";
import { session } from "@web/session";

/**
 * Theme Service
 * Manages the dark/light mode theme based on user preference
 */
export const themeService = {
    dependencies: ["orm"],

    async start(env, { orm }) {
        const applyTheme = async () => {
            try {
                // Get user's theme preference from backend
                const result = await orm.call(
                    "res.users",
                    "get_user_theme_preference",
                    []
                );

                const body = document.body;

                // Apply or remove dark mode class
                if (result === "dark") {
                    body.classList.add("o_dark_mode");
                } else {
                    body.classList.remove("o_dark_mode");
                }

                // Store in session storage for quick access
                browser.sessionStorage.setItem("theme_preference", result);
            } catch (error) {
                console.error("Failed to apply theme:", error);
                // Default to dark mode on error
                document.body.classList.add("o_dark_mode");
            }
        };

        // Apply theme on startup
        await applyTheme();

        return {
            applyTheme,
        };
    },
};

registry.category("services").add("theme", themeService);
