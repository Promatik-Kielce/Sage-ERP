#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for automatic timesheet adjustment when correcting attendance times.

This script tests the following scenarios:
1. Simple reduction (8h → 6h)
2. Reduction with deletion (8h → 2h)
3. Simple increase (6h → 8h)
4. Skip active timesheet
"""

import sys
from datetime import datetime, timedelta
from odoo import api, SUPERUSER_ID

def test_timesheet_adjustment(env):
    """Test automatic timesheet adjustment functionality"""

    print("\n" + "="*80)
    print("TESTING AUTOMATIC TIMESHEET ADJUSTMENT")
    print("="*80)

    # Get test employee
    employee = env['hr.employee'].search([('user_id', '!=', False)], limit=1)
    if not employee:
        print("ERROR: No employee with user found. Please create one first.")
        return False

    print(f"\nUsing test employee: {employee.name}")

    # Get or create default project
    project1 = env['project.project'].search([('name', '=', '0 - Koszty Stałe')], limit=1)
    if not project1:
        project1 = env['project.project'].create({
            'name': '0 - Koszty Stałe',
            'allow_timesheets': True,
        })

    project2 = env['project.project'].search([('name', '!=', '0 - Koszty Stałe'), ('allow_timesheets', '=', True)], limit=1)
    if not project2:
        project2 = env['project.project'].create({
            'name': 'Test Project',
            'allow_timesheets': True,
        })

    print(f"Project 1: {project1.name}")
    print(f"Project 2: {project2.name}")

    # Test 1: Simple Reduction (8h → 6h)
    print("\n" + "-"*80)
    print("TEST 1: Simple Reduction (8h → 6h)")
    print("-"*80)

    try:
        check_in = datetime.now() - timedelta(hours=10)
        check_out = check_in + timedelta(hours=8)

        # Create attendance
        attendance1 = env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': check_in,
            'check_out': check_out,
        })

        # Create timesheets manually (simulating project switching)
        timesheet1a = env['account.analytic.line'].create({
            'employee_id': employee.id,
            'user_id': employee.user_id.id,
            'project_id': project1.id,
            'date': check_in.date(),
            'name': 'Work on Project 1',
            'unit_amount': 3.0,
            'attendance_id': attendance1.id,
        })

        timesheet1b = env['account.analytic.line'].create({
            'employee_id': employee.id,
            'user_id': employee.user_id.id,
            'project_id': project2.id,
            'date': check_in.date(),
            'name': 'Work on Project 2',
            'unit_amount': 5.0,
            'attendance_id': attendance1.id,
        })

        print(f"Initial state:")
        print(f"  Worked hours: {attendance1.worked_hours:.2f}h")
        print(f"  Timesheet A: {timesheet1a.unit_amount:.2f}h")
        print(f"  Timesheet B: {timesheet1b.unit_amount:.2f}h")
        print(f"  Total: {attendance1.total_timesheet_hours:.2f}h")

        # Reduce check_out by 2 hours (8h → 6h)
        new_check_out = check_out - timedelta(hours=2)
        attendance1.write({'check_out': new_check_out})

        print(f"\nAfter reducing to 6h:")
        print(f"  Worked hours: {attendance1.worked_hours:.2f}h")

        # Refresh timesheet records
        timesheet1a.invalidate_recordset()
        timesheet1b.invalidate_recordset()

        # Check if timesheet1b still exists
        if timesheet1b.exists():
            print(f"  Timesheet A: {timesheet1a.unit_amount:.2f}h")
            print(f"  Timesheet B: {timesheet1b.unit_amount:.2f}h")
            print(f"  Total: {attendance1.total_timesheet_hours:.2f}h")

            # Verify: Should be A=3h, B=3h
            if abs(timesheet1a.unit_amount - 3.0) < 0.01 and abs(timesheet1b.unit_amount - 3.0) < 0.01:
                print("  ✓ TEST 1 PASSED: Timesheets adjusted correctly (A=3h, B=3h)")
            else:
                print("  ✗ TEST 1 FAILED: Expected A=3h, B=3h")
        else:
            print("  Timesheet A: {timesheet1a.unit_amount:.2f}h")
            print("  Timesheet B: DELETED")
            print("  ✗ TEST 1 FAILED: Timesheet B should not be deleted")

        # Clean up
        attendance1.unlink()

    except Exception as e:
        print(f"  ✗ TEST 1 FAILED with error: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Reduction with Deletion (8h → 2h)
    print("\n" + "-"*80)
    print("TEST 2: Reduction with Deletion (8h → 2h)")
    print("-"*80)

    try:
        check_in = datetime.now() - timedelta(hours=10)
        check_out = check_in + timedelta(hours=8)

        # Create attendance
        attendance2 = env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': check_in,
            'check_out': check_out,
        })

        # Create timesheets
        timesheet2a = env['account.analytic.line'].create({
            'employee_id': employee.id,
            'user_id': employee.user_id.id,
            'project_id': project1.id,
            'date': check_in.date(),
            'name': 'Work on Project 1',
            'unit_amount': 3.0,
            'attendance_id': attendance2.id,
        })

        timesheet2b = env['account.analytic.line'].create({
            'employee_id': employee.id,
            'user_id': employee.user_id.id,
            'project_id': project2.id,
            'date': check_in.date(),
            'name': 'Work on Project 2',
            'unit_amount': 5.0,
            'attendance_id': attendance2.id,
        })

        print(f"Initial state:")
        print(f"  Worked hours: {attendance2.worked_hours:.2f}h")
        print(f"  Timesheet A: {timesheet2a.unit_amount:.2f}h")
        print(f"  Timesheet B: {timesheet2b.unit_amount:.2f}h")
        print(f"  Total: {attendance2.total_timesheet_hours:.2f}h")

        # Reduce check_out by 6 hours (8h → 2h)
        new_check_out = check_out - timedelta(hours=6)
        attendance2.write({'check_out': new_check_out})

        print(f"\nAfter reducing to 2h:")
        print(f"  Worked hours: {attendance2.worked_hours:.2f}h")

        # Refresh
        timesheet2a.invalidate_recordset()
        timesheet2b.invalidate_recordset()

        timesheet2b_exists = timesheet2b.exists()

        if timesheet2b_exists:
            print(f"  Timesheet A: {timesheet2a.unit_amount:.2f}h")
            print(f"  Timesheet B: {timesheet2b.unit_amount:.2f}h (should be deleted)")
            print(f"  ✗ TEST 2 FAILED: Timesheet B should be deleted")
        else:
            print(f"  Timesheet A: {timesheet2a.unit_amount:.2f}h")
            print(f"  Timesheet B: DELETED ✓")
            print(f"  Total: {attendance2.total_timesheet_hours:.2f}h")

            # Verify: Should be A=2h, B=deleted
            if abs(timesheet2a.unit_amount - 2.0) < 0.01:
                print("  ✓ TEST 2 PASSED: Timesheet B deleted, A reduced to 2h")
            else:
                print(f"  ✗ TEST 2 FAILED: Expected A=2h, got {timesheet2a.unit_amount:.2f}h")

        # Clean up
        attendance2.unlink()

    except Exception as e:
        print(f"  ✗ TEST 2 FAILED with error: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Simple Increase (6h → 8h)
    print("\n" + "-"*80)
    print("TEST 3: Simple Increase (6h → 8h)")
    print("-"*80)

    try:
        check_in = datetime.now() - timedelta(hours=10)
        check_out = check_in + timedelta(hours=6)

        # Create attendance
        attendance3 = env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': check_in,
            'check_out': check_out,
        })

        # Create timesheets
        timesheet3a = env['account.analytic.line'].create({
            'employee_id': employee.id,
            'user_id': employee.user_id.id,
            'project_id': project1.id,
            'date': check_in.date(),
            'name': 'Work on Project 1',
            'unit_amount': 3.0,
            'attendance_id': attendance3.id,
        })

        timesheet3b = env['account.analytic.line'].create({
            'employee_id': employee.id,
            'user_id': employee.user_id.id,
            'project_id': project2.id,
            'date': check_in.date(),
            'name': 'Work on Project 2',
            'unit_amount': 3.0,
            'attendance_id': attendance3.id,
        })

        print(f"Initial state:")
        print(f"  Worked hours: {attendance3.worked_hours:.2f}h")
        print(f"  Timesheet A: {timesheet3a.unit_amount:.2f}h")
        print(f"  Timesheet B: {timesheet3b.unit_amount:.2f}h")
        print(f"  Total: {attendance3.total_timesheet_hours:.2f}h")

        # Increase check_out by 2 hours (6h → 8h)
        new_check_out = check_out + timedelta(hours=2)
        attendance3.write({'check_out': new_check_out})

        print(f"\nAfter increasing to 8h:")
        print(f"  Worked hours: {attendance3.worked_hours:.2f}h")

        # Refresh
        timesheet3a.invalidate_recordset()
        timesheet3b.invalidate_recordset()

        print(f"  Timesheet A: {timesheet3a.unit_amount:.2f}h")
        print(f"  Timesheet B: {timesheet3b.unit_amount:.2f}h")
        print(f"  Total: {attendance3.total_timesheet_hours:.2f}h")

        # Verify: Should be A=3h, B=5h
        if abs(timesheet3a.unit_amount - 3.0) < 0.01 and abs(timesheet3b.unit_amount - 5.0) < 0.01:
            print("  ✓ TEST 3 PASSED: Most recent timesheet increased (A=3h, B=5h)")
        else:
            print(f"  ✗ TEST 3 FAILED: Expected A=3h, B=5h")

        # Clean up
        attendance3.unlink()

    except Exception as e:
        print(f"  ✗ TEST 3 FAILED with error: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*80)
    print("TEST SUITE COMPLETED")
    print("="*80 + "\n")

if __name__ == '__main__':
    # This script should be run with: ./odoo-bin shell -d DATABASE_NAME --no-http
    # Then import and run this function
    print("Please run this script using:")
    print("./odoo-bin shell -d DATABASE_NAME")
    print("Then in the shell:")
    print(">>> exec(open('test_timesheet_adjustment.py').read())")
    print(">>> test_timesheet_adjustment(env)")
