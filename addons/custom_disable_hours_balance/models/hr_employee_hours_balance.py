from odoo import api, models


class HrEmployeeHoursBalanceLine(models.Model):
    _inherit = "hr.employee.hours.balance.line"

    @api.model
    def search_read(self, domain=None, fields=None, offset=0, limit=None, order=None):
        return []

    def read(self, fields=None, load="_classic_read"):
        return []

    @api.model
    def search_fetch(self, domain, field_names=None, offset=0, limit=None, order=None):
        return self.browse()

    def export_data(self, fields_to_export):
        return {"datas": []}

    @api.model
    def web_search_read(self, domain=None, specification=None, offset=0, limit=None, order=None, count_limit=None):
        return {
            "length": 0,
            "records": [],
        }

    @api.model
    def formatted_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        return []

    @api.model
    def web_read_group(self, domain, groupby, aggregates=(), limit=None, offset=0, order=None, **kwargs):
        return {
            "groups": [],
            "length": 0,
        }

    @api.model
    def _read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None):
        return []

    @api.model
    def _read_grouping_sets(self, domain, grouping_sets=(), aggregates=(), order=None):
        return []