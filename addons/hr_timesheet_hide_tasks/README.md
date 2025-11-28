# Hide Task Timesheets

## Overview

This module hides all task-based timesheet UI elements while preserving the attendance-based timesheet workflow provided by `hr_attendance_timesheet_project`.

## Purpose

Your organization uses **attendance-based timesheets exclusively**. Employees check in/out via the attendance system, and timesheets are automatically created. The task-based timesheet UI creates confusion and UI clutter that this module eliminates.

## What This Module Does

### UI Elements Hidden

**Task Views:**
- ✓ "Timesheets" tab in task forms
- ✓ Allocated hours section in task headers
- ✓ All timesheet columns in task lists (allocated, effective, remaining, progress)
- ✓ Timesheet progress badges in kanban view
- ✓ "Timesheets 80%" and ">100%" search filters

**Timesheet Views:**
- ✓ task_id field in timesheet forms/lists
- ✓ "Group by Task" filter

**Menus:**
- ✓ "Timesheets / Reporting / By Task" menu item

## What This Module Does NOT Do

- ❌ Does not delete any data
- ❌ Does not modify core Odoo code
- ❌ Does not affect the attendance-based timesheet workflow
- ❌ Does not prevent technical users from accessing hidden fields

## Technical Implementation

Uses Odoo's standard extension mechanisms:
- **View Inheritance**: XPath expressions to hide UI elements without affecting field access
- **Menu Deactivation**: Sets `active=False` on task reporting menu

Fields remain accessible and compute normally - only the UI is hidden. This prevents view parser errors and maintains full compatibility with existing workflows.

## Installation

1. **Update module list:**
   ```bash
   ./odoo-bin -d your_database -u base --stop-after-init
   ```

2. **Install module:**
   ```bash
   ./odoo-bin -d your_database -i hr_timesheet_hide_tasks --stop-after-init
   ```

3. **Restart Odoo:**
   ```bash
   ./odoo-bin -d your_database
   ```

## Verification

After installation, verify:

1. Open any task → No "Timesheets" tab visible
2. View task list → No timesheet columns visible
3. Create timesheet → No task_id field visible
4. Check in/out via attendance → Timesheets still created correctly
5. View project totals → Hours still calculate from attendance timesheets

## Rollback

To restore original UI:

1. **Uninstall module:**
   ```bash
   ./odoo-bin -d your_database --uninstall hr_timesheet_hide_tasks --stop-after-init
   ```

2. All UI elements return immediately
3. Zero data loss - all data remains intact

## Compatibility

- **Required modules:** `hr_timesheet`, `hr_attendance_timesheet_project`
- **Odoo version:** 19.0
- **Optional compatibility:** Works with `sale_timesheet` but you may want additional customization

## Benefits

✅ **Cleaner UI** - Tasks focused on project management, not time tracking
✅ **No confusion** - Clear separation: attendance = timesheets, tasks = work tracking
✅ **Data preserved** - All historical information intact
✅ **Reversible** - Can undo with simple module uninstall
✅ **Upgrade safe** - View inheritance pattern survives Odoo updates
✅ **Low risk** - No core code modifications

## Support

For issues or questions, consult the implementation plan in your documentation directory.

## License

LGPL-3
