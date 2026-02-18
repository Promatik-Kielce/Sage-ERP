# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class ProjectProject(models.Model):
    _inherit = 'project.project'
    _order = 'project_number asc, sequence asc, name asc, id asc'

    project_number = fields.Char(
        string='Project Number',
        required=True,
        copy=False,              # Don't duplicate when copying projects
        index='btree_not_null',  # Fast searching
        tracking=True,           # Track changes in chatter
        default_export_compatible=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('project.project.number') or _('New'),
    )

    # Database-level constraint (integrity enforcement)
    _project_number_unique = models.UniqueIndex(
        '(project_number)',
        'A project with this number already exists.'
    )

    @api.constrains('project_number')
    def _check_project_number_unique(self):
        """Ensure project number is globally unique."""
        for project in self:
            if project.project_number:
                duplicate = self.search([
                    ('id', '!=', project.id),
                    ('project_number', '=', project.project_number)
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        _('Project number "%s" is already used by project "%s".',
                          project.project_number, duplicate.name)
                    )

    @api.constrains('project_number')
    def _check_project_number_format(self):
        """Ensure project number isn't empty/whitespace."""
        for project in self:
            if project.project_number and not project.project_number.strip():
                raise ValidationError(
                    _('Project number cannot be empty or whitespace only.')
                )

    @api.depends('project_number', 'name')
    def _compute_display_name(self):
        """Display projects as 'number - name'."""
        for project in self:
            if project.project_number:
                project.display_name = f"{project.project_number} - {project.name}"
            else:
                # Fallback for edge cases during creation
                project.display_name = project.name

    @api.model
    def _search_display_name(self, operator, value):
        """Allow searching by both number and name."""
        if operator in ['=', '!=', 'like', 'ilike', 'in', 'not in']:
            return ['|', ('project_number', operator, value), ('name', operator, value)]
        return NotImplemented
