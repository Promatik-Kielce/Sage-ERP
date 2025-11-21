# -*- coding: utf-8 -*-
# Part of Sage-ERP. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # The attendance_manager_id is a related field from employee_id.attendance_manager_id
    # By extending hr.employee field access, this should automatically be accessible
    # This file exists for future extensions if needed
