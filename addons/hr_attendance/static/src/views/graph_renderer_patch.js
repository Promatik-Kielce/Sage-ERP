/** @odoo-module **/

import { GraphRenderer } from "@web/views/graph/graph_renderer";
import { patch } from "@web/core/utils/patch";

patch(GraphRenderer.prototype, {
    /**
     * Override to customize chart colors for balance charts
     */
    getChartConfig() {
        const config = super.getChartConfig();

        // Only apply custom coloring for balance charts
        if (this.props.model.metaData.resModel === 'hr.employee.hours.balance.line') {
            // Prevent pie chart for balance views - it doesn't make sense for time series data
            if (config.type === 'pie' || config.type === 'doughnut') {
                config.type = 'bar';  // Force to bar chart instead
            }
            const datasets = config.data.datasets;

            // Get the measures being displayed
            const measures = this.props.model.metaData.measures;
            let measureFields = [];

            // Handle different formats of measures
            if (measures) {
                if (Array.isArray(measures)) {
                    measureFields = measures.map(m => m.fieldName || m);
                } else if (typeof measures === 'object') {
                    measureFields = Object.keys(measures);
                }
            }

            // Apply custom colors based on field name
            datasets.forEach((dataset, index) => {
                const fieldName = dataset.label || '';

                // Check if this dataset is for balance_delta or balance_cumulative
                const isBalanceField =
                    measureFields.includes('balance_delta') ||
                    measureFields.includes('balance_cumulative') ||
                    fieldName.includes('Balance') ||
                    fieldName.includes('Bilans') ||
                    fieldName.includes('+/-') ||
                    fieldName.includes('Total') ||
                    fieldName.includes('Dzienny');

                if (isBalanceField) {
                    const data = dataset.data;

                    // Check if this is a line chart
                    const isLineChart = config.type === 'line' || dataset.type === 'line';

                    if (isLineChart) {
                        // For line charts, we need to handle positive/negative differently
                        // Store the original data reference
                        dataset._originalData = [...data];

                        // Calculate colors based on segments
                        const segmentColors = {
                            backgroundColor: (context) => {
                                if (!context.parsed) return 'rgba(108, 117, 125, 0.3)';
                                const value = context.parsed.y;
                                if (value < 0) return 'rgba(220, 53, 69, 0.3)';
                                if (value > 0) return 'rgba(40, 167, 69, 0.3)';
                                return 'rgba(108, 117, 125, 0.3)';
                            },
                            borderColor: (context) => {
                                if (!context.parsed) return 'rgba(108, 117, 125, 1)';
                                const value = context.parsed.y;
                                if (value < 0) return 'rgba(220, 53, 69, 1)';
                                if (value > 0) return 'rgba(40, 167, 69, 1)';
                                return 'rgba(108, 117, 125, 1)';
                            },
                            segment: {
                                backgroundColor: (context) => {
                                    const value = context.p1.parsed.y;
                                    if (value < 0) return 'rgba(220, 53, 69, 0.3)';
                                    if (value > 0) return 'rgba(40, 167, 69, 0.3)';
                                    return 'rgba(108, 117, 125, 0.3)';
                                },
                                borderColor: (context) => {
                                    const value = context.p1.parsed.y;
                                    if (value < 0) return 'rgba(220, 53, 69, 1)';
                                    if (value > 0) return 'rgba(40, 167, 69, 1)';
                                    return 'rgba(108, 117, 125, 1)';
                                }
                            }
                        };

                        dataset.fill = 'origin';
                        dataset.backgroundColor = segmentColors.backgroundColor;
                        dataset.borderColor = segmentColors.borderColor;
                        dataset.segment = segmentColors.segment;
                        dataset.borderWidth = 3;
                        dataset.pointBackgroundColor = (context) => {
                            const value = context.parsed?.y;
                            if (value < 0) return 'rgba(220, 53, 69, 0.8)';
                            if (value > 0) return 'rgba(40, 167, 69, 0.8)';
                            return 'rgba(108, 117, 125, 0.8)';
                        };
                        dataset.pointBorderColor = (context) => {
                            const value = context.parsed?.y;
                            if (value < 0) return 'rgba(220, 53, 69, 1)';
                            if (value > 0) return 'rgba(40, 167, 69, 1)';
                            return 'rgba(108, 117, 125, 1)';
                        };
                        dataset.pointRadius = 4;
                        dataset.pointHoverRadius = 6;
                        dataset.tension = 0.3;
                    } else {
                        // For bar charts, color each bar individually
                        const backgroundColors = [];
                        const borderColors = [];

                        data.forEach((value) => {
                            if (value < 0) {
                                backgroundColors.push('rgba(220, 53, 69, 0.8)');
                                borderColors.push('rgba(220, 53, 69, 1)');
                            } else if (value > 0) {
                                backgroundColors.push('rgba(40, 167, 69, 0.8)');
                                borderColors.push('rgba(40, 167, 69, 1)');
                            } else {
                                backgroundColors.push('rgba(108, 117, 125, 0.8)');
                                borderColors.push('rgba(108, 117, 125, 1)');
                            }
                        });

                        dataset.backgroundColor = backgroundColors;
                        dataset.borderColor = borderColors;
                        dataset.borderWidth = 2;
                    }
                }
            });
        }

        return config;
    },
});
