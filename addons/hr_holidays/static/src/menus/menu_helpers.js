                       /** @odoo-module **/

import { computeAppsAndMenuItems as originalComputeAppsAndMenuItems } from "@web/webclient/menus/menu_helpers";

// Override computeAppsAndMenuItems to hide hr_holidays menu from app list
export function computeAppsAndMenuItems(menuTree) {
    const result = originalComputeAppsAndMenuItems(menuTree);
    
    // Hide hr_holidays menu from app list (xmlid: menu_hr_holidays_root)
    result.apps = result.apps.filter(
        (app) => app.xmlid !== "hr_holidays.menu_hr_holidays_root"
    );
    
    return result;
}
