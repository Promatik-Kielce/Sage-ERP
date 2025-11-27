# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # Hide timesheet fields from search/filter/groupby builders
    # Fields still compute normally, just invisible to standard users
    # Only "Technical Features" group (base.group_no_one) can see them
    timesheet_ids = fields.One2many(groups="base.group_no_one")
    effective_hours = fields.Float(groups="base.group_no_one")
    allocated_hours = fields.Float(groups="base.group_no_one")
    remaining_hours = fields.Float(groups="base.group_no_one")
    progress = fields.Float(groups="base.group_no_one")
    overtime = fields.Float(groups="base.group_no_one")
    subtask_effective_hours = fields.Float(groups="base.group_no_one")
    total_hours_spent = fields.Float(groups="base.group_no_one")
    remaining_hours_percentage = fields.Float(groups="base.group_no_one")
