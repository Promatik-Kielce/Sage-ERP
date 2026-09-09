# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models

from .ir_attachment import FORCE_UNLINK_CTX


class ProjectProject(models.Model):
    _inherit = 'project.project'

    def unlink(self):
        # See `project.task.unlink`: let the attachments of a deleted project be
        # really destroyed rather than soft deleted onto a dangling record.
        return super(ProjectProject, self.with_context(**{FORCE_UNLINK_CTX: True})).unlink()
