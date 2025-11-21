# -*- coding: utf-8 -*-
# Part of Sage-ERP. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    # Extend field access to include our employee reader group
    # This allows regular employees to VIEW these fields (read-only)

    attendance_manager_id = fields.Many2one(
        groups="hr_attendance.group_hr_attendance_officer,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    attendance_ids = fields.One2many(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    last_attendance_id = fields.Many2one(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    last_check_in = fields.Datetime(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    last_check_out = fields.Datetime(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    attendance_state = fields.Selection(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    hours_last_month = fields.Float(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    hours_last_month_display = fields.Char(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    hours_today = fields.Float(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )

    total_overtime = fields.Float(
        groups="hr_attendance.group_hr_attendance_officer,hr.group_hr_user,hr_attendance_employee_access.group_hr_attendance_all_reader"
    )
