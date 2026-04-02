from odoo import api, models, _
from odoo.exceptions import AccessError


class HrHoursBalanceAdjustment(models.Model):
    _inherit = "hr.hours.balance.adjustment"

    @api.model
    def search(self, domain, offset=0, limit=None, order=None):
        return self.browse()

    @api.model
    def search_count(self, domain):
        return 0

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        return []

    def read(self, fields=None, load="_classic_read"):
        return []

    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None):
        return {
            "length": 0,
            "records": [],
        }

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        return []

    @api.model_create_multi
    def create(self, vals_list):
        raise AccessError(_("Hours Balance adjustments are disabled."))

    def write(self, vals):
        raise AccessError(_("Hours Balance adjustments are disabled."))

    def unlink(self):
        raise AccessError(_("Hours Balance adjustments are disabled."))