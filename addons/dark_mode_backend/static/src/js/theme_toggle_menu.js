/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Theme Toggle Menu Item
 * Adds a theme switcher to the user menu
 */
export class ThemeToggleMenu extends Component {
    static template = "dark_mode_backend.ThemeToggleMenu";

    setup() {
        this.orm = useService("orm");
        this.user = useService("user");
        this.theme = useService("theme");
    }

    async toggleTheme() {
        const currentTheme = this.user.context.theme_preference || "dark";
        const newTheme = currentTheme === "dark" ? "light" : "dark";

        try {
            // Update user preference in database
            await this.orm.write("res.users", [this.user.userId], {
                theme_preference: newTheme,
            });

            // Update context
            this.user.context.theme_preference = newTheme;

            // Apply theme immediately
            await this.theme.applyTheme();
        } catch (error) {
            console.error("Failed to toggle theme:", error);
        }
    }

    get currentTheme() {
        return this.user.context.theme_preference || "dark";
    }

    get isDarkMode() {
        return this.currentTheme === "dark";
    }
}

registry.category("user_menuitems").add("theme_toggle", {
    Component: ThemeToggleMenu,
    sequence: 1,
});
