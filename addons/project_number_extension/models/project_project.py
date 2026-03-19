from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class ProjectProject(models.Model):
    _inherit = 'project.project'
    _order = 'is_favorite desc, project_number asc, sequence asc, name asc, id asc'

    project_number = fields.Char(
        string='Project Number',
        required=True,
        copy=False,
        index='btree_not_null',
        tracking=True,
        default_export_compatible=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('project.project.number') or _('New'),
    )

    _project_number_unique = models.UniqueIndex(
        '(project_number)',
        'A project with this number already exists.'
    )

    @api.constrains('project_number')
    def _check_project_number_unique(self):
        for project in self:
            if not project.project_number:
                continue

            duplicate = self.with_context(active_test=False).search([
                ('id', '!=', project.id),
                ('project_number', '=', project.project_number),
            ], limit=1)

            if duplicate:
                raise ValidationError(
                    _('Project number "%s" is already used by project "%s".') %
                    (project.project_number, duplicate.name)
                )

    @api.constrains('project_number')
    def _check_project_number_format(self):
        for project in self:
            if project.project_number and not project.project_number.strip():
                raise ValidationError(
                    _('Project number cannot be empty or whitespace only.')
                )

    @api.depends('project_number', 'name')
    def _compute_display_name(self):
        for project in self:
            if project.project_number:
                project.display_name = f"{project.project_number} - {project.name}"
            else:
                project.display_name = project.name

    @api.model
    def _search_display_name(self, operator, value):
        if operator in ['=', '!=', 'like', 'ilike', '=like', '=ilike', 'not like', 'not ilike']:
            return ['|', ('project_number', operator, value), ('name', operator, value)]
        return super()._search_display_name(operator, value)