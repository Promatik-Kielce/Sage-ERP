# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models

from .ir_attachment import FORCE_UNLINK_CTX


class ProjectTask(models.Model):
    _inherit = 'project.task'

    def unlink(self):
        # `BaseModel.unlink` sweeps the attachments of the record by
        # (res_model, res_id); without this the files of a deleted task would be
        # parked in the recycle bin of a record that no longer exists. The audit
        # rows survive on their own: `task_id` is `ondelete='set null'` and the
        # file name, size and checksum are stored on them.
        return super(ProjectTask, self.with_context(**{FORCE_UNLINK_CTX: True})).unlink()
