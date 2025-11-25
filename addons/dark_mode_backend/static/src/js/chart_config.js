/** @odoo-module **/

import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

/**
 * Chart.js Dark Mode Configuration
 * Configures Chart.js to use light colors in dark mode
 */

// Wait for Chart.js to be available
const setupChartDefaults = () => {
    if (typeof Chart === 'undefined') {
        // Chart.js not loaded yet, try again later
        setTimeout(setupChartDefaults, 100);
        return;
    }

    // Check if dark mode is active
    const isDarkMode = document.body.classList.contains('o_dark_mode');

    if (isDarkMode) {
        // Configure default colors for dark mode
        Chart.defaults.color = '#e9f0f2'; // Light text color
        Chart.defaults.borderColor = '#666'; // Medium gray borders
        Chart.defaults.backgroundColor = 'rgba(131, 216, 174, 0.2)'; // Primary color with transparency

        // Configure scale (axes) defaults
        if (Chart.defaults.scale) {
            Chart.defaults.scale.grid = {
                ...Chart.defaults.scale.grid,
                color: '#444', // Lighter grid lines
            };
            Chart.defaults.scale.ticks = {
                ...Chart.defaults.scale.ticks,
                color: '#e9f0f2', // Light tick labels
            };
        }

        // Configure legend defaults
        if (Chart.defaults.plugins && Chart.defaults.plugins.legend) {
            Chart.defaults.plugins.legend.labels = {
                ...Chart.defaults.plugins.legend.labels,
                color: '#e9f0f2', // Light legend text
            };
        }

        // Configure tooltip defaults
        if (Chart.defaults.plugins && Chart.defaults.plugins.tooltip) {
            Chart.defaults.plugins.tooltip = {
                ...Chart.defaults.plugins.tooltip,
                backgroundColor: '#262A36',
                titleColor: '#e9f0f2',
                bodyColor: '#e9f0f2',
                borderColor: '#666',
                borderWidth: 1,
            };
        }
    }
};

// Setup when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupChartDefaults);
} else {
    setupChartDefaults();
}

// Export for module system
export default {
    setupChartDefaults
};
