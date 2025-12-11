#!/usr/bin/env python3
# Quick inline test for timesheet adjustment
from datetime import datetime, timedelta

# Test employee
employee = env['hr.employee'].search([('user_id', '!=', False)], limit=1)
if not employee:
    raise Exception("No employee found")

print(f"Testing with employee: {employee.name}")

# Get projects
project1 = env['project.project'].search([('allow_timesheets', '=', True)], limit=1)
project2 = env['project.project'].search([('allow_timesheets', '=', True), ('id', '!=', project1.id)], limit=1)

print(f"Project 1: {project1.name}")
print(f"Project 2: {project2.name}")

# Test 1: Simple Reduction
print("\n=== TEST 1: Reduction 8h → 6h ===")
check_in = datetime.now() - timedelta(hours=10)
check_out = check_in + timedelta(hours=8)

att = env['hr.attendance'].create({
    'employee_id': employee.id,
    'check_in': check_in,
    'check_out': check_out,
})

# Create 2 timesheets
ts1 = env['account.analytic.line'].create({
    'employee_id': employee.id,
    'user_id': employee.user_id.id,
    'project_id': project1.id,
    'date': check_in.date(),
    'name': 'Test 1',
    'unit_amount': 3.0,
    'attendance_id': att.id,
})

ts2 = env['account.analytic.line'].create({
    'employee_id': employee.id,
    'user_id': employee.user_id.id,
    'project_id': project2.id,
    'date': check_in.date(),
    'name': 'Test 2',
    'unit_amount': 5.0,
    'attendance_id': att.id,
})

print(f"Before: worked={att.worked_hours:.2f}h, ts1={ts1.unit_amount:.2f}h, ts2={ts2.unit_amount:.2f}h")

# Reduce to 6h
att.write({'check_out': check_out - timedelta(hours=2)})

ts1.invalidate_recordset()
ts2.invalidate_recordset()

print(f"After:  worked={att.worked_hours:.2f}h, ts1={ts1.unit_amount:.2f}h, ts2={ts2.unit_amount:.2f}h")

if abs(ts1.unit_amount - 3.0) < 0.01 and abs(ts2.unit_amount - 3.0) < 0.01:
    print("✓ PASS")
else:
    print("✗ FAIL")

print(f"Attendance ID: {att.id}")
