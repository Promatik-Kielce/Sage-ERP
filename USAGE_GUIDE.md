# Automatic Timesheet Adjustment - Usage Guide

## What Changed?

When managers correct attendance check-in/check-out times, **timesheets now automatically adjust** to match the new worked hours.

## Before vs After

### Before (Old Behavior)
```
Manager corrects attendance: 8h → 6h
↓
❌ ERROR: "Timesheet hours exceed worked hours"
↓
Manager must manually reduce timesheet entries
↓
Then retry attendance correction
```

### After (New Behavior)
```
Manager corrects attendance: 8h → 6h
↓
✅ Timesheets automatically adjusted (LIFO)
↓
Save successful - no manual intervention needed
```

## How It Works

### Reduction (Decreasing Hours)
**Strategy**: Last-In-First-Out (LIFO)

**Example**: Attendance 8h → 6h
- Timesheet A: 3h (created first)
- Timesheet B: 5h (created later)

**Result**: B reduced to 3h, A unchanged

### Increase (Increasing Hours)
**Strategy**: Extend most recent

**Example**: Attendance 6h → 8h
- Timesheet A: 3h
- Timesheet B: 3h (most recent)

**Result**: B increased to 5h, A unchanged

### Deletion
**When**: Reduction exceeds timesheet hours

**Example**: Attendance 8h → 2h
- Timesheet A: 3h
- Timesheet B: 5h

**Result**: B deleted, A reduced to 2h

## User Actions

### For Managers
1. Open attendance record
2. Edit check_in or check_out time
3. Click Save
4. ✅ **Done!** Timesheets adjusted automatically

### For Employees
No changes - check-in/check-out works exactly as before.

## Important Notes

### ✅ What's Adjusted
- Closed timesheets (completed work)
- Only when editing already checked-out attendance
- Only significant changes (> 0.01h)

### ❌ What's NOT Adjusted
- Active timesheet (employee still checked in)
- New check-outs (normal check-out flow unchanged)
- Very small changes (< 0.01h ignored)

## Examples

### Example 1: Simple Correction
```
Employee forgot to check out on time
Actual checkout: 17:00 (8 hours)
Corrected to: 16:00 (7 hours)

Before: Project X = 8h
After:  Project X = 7h ✅ (automatically adjusted)
```

### Example 2: Multiple Projects
```
Employee worked on 2 projects
Original: 09:00-17:00 (8h)
  - Project A: 3h
  - Project B: 5h

Corrected to: 09:00-15:00 (6h)

After adjustment:
  - Project A: 3h (unchanged)
  - Project B: 3h (reduced by 2h) ✅
```

### Example 3: Large Correction
```
Original: 09:00-17:00 (8h)
  - Project A: 3h
  - Project B: 5h

Corrected to: 09:00-11:00 (2h)

After adjustment:
  - Project A: 2h (reduced by 1h)
  - Project B: DELETED ✅
```

### Example 4: Employee Still Working
```
Employee checked in but not out yet
Active timesheet: Project X = 0h (still tracking)
Previous closed: Project Y = 3h

Correct earlier work: 8h → 6h

After adjustment:
  - Project Y: 1h (reduced by 2h) ✅
  - Project X: 0h (unchanged - still active)
```

## Deployment

### Update Module
After deploying code changes, update the module:

```bash
./odoo-bin -d YOUR_DATABASE -u hr_attendance_timesheet_project --stop-after-init
```

### Verify Installation
1. Create test attendance with 8h
2. Add 2 timesheets (3h + 5h)
3. Edit attendance to 6h
4. Save and verify ts2 = 3h ✅

## Troubleshooting

### Issue: Adjustment didn't happen
**Check**:
- Was attendance already checked out? (Must be closed)
- Was change significant? (> 0.01h required)
- Are there closed timesheets? (Active ones excluded)

### Issue: Validation error still appears
**Cause**: Adjustment couldn't reduce enough (rare edge case)
**Solution**: Manually adjust or contact support

### Issue: Wrong timesheet adjusted
**Note**: System adjusts most recently created timesheet first
**Check**: Timesheet creation order (not project order)

## Support

For issues or questions:
1. Check [IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md) for technical details
2. Review test scripts: `test_timesheet_adjustment.py`, `test_inline.py`
3. Contact system administrator

## Rollback

If needed, restore previous behavior:
```bash
git checkout HEAD~1 addons/hr_attendance_timesheet_project/models/hr_attendance.py
./odoo-bin -d YOUR_DATABASE -u hr_attendance_timesheet_project --stop-after-init
```
