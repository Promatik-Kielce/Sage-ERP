# Part of Sage-ERP. See LICENSE file for full copyright and licensing details.

from odoo import fields, models, _
from odoo.exceptions import ValidationError

# Valid attributes for gantt view element
GANTT_VALID_ATTRIBUTES = {
    '__validate__',
    'class',
    'js_class',
    'string',
    'date_start',
    'date_stop',
    'date_delay',
    'default_scale',
    'color',
    'progress',
    'default_group_by',
    'precision',
    'create',
    'edit',
    'delete',
    'scales',
    'templates',
    'consolidation',
    'consolidation_max',
    'consolidation_exclude',
    'offset',
    'cell_create',
    'cell_edit',
    'plan',
    'on_create',
    'on_edit',
    'on_delete',
    'disable_drag_drop',
    'display_unavailability',
    'total_row',
}


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    type = fields.Selection(selection_add=[('gantt', "Gantt")], ondelete={'gantt': 'cascade'})

    def _is_qweb_based_view(self, view_type):
        """Gantt views use QWeb templates for rendering."""
        return super()._is_qweb_based_view(view_type) or view_type == 'gantt'

    def _validate_tag_gantt(self, node, name_manager, node_info):
        """Validate gantt view architecture."""
        if not node_info['validate']:
            return

        # Validate required attributes
        if not node.get('date_start'):
            msg = _('Gantt view must have a "date_start" attribute')
            self._raise_view_error(msg, node)

        if not node.get('date_stop') and not node.get('date_delay'):
            msg = _('Gantt view must have either "date_stop" or "date_delay" attribute')
            self._raise_view_error(msg, node)

        # Validate only allowed attributes
        remaining = set(node.attrib) - GANTT_VALID_ATTRIBUTES
        if remaining:
            msg = _(
                "Invalid attributes (%(invalid)s) in gantt view. Allowed attributes: %(valid)s",
                invalid=', '.join(remaining),
                valid=', '.join(sorted(GANTT_VALID_ATTRIBUTES))
            )
            self._raise_view_error(msg, node)

        # Validate scale if specified
        valid_scales = {'day', 'week', 'month', 'year'}
        default_scale = node.get('default_scale')
        if default_scale and default_scale not in valid_scales:
            msg = _(
                'Invalid default_scale "%(scale)s". Must be one of: %(valid)s',
                scale=default_scale,
                valid=', '.join(valid_scales)
            )
            self._raise_view_error(msg, node)

    def _get_view_info(self):
        """Add gantt view icon information."""
        return {'gantt': {'icon': 'fa fa-tasks'}} | super()._get_view_info()
