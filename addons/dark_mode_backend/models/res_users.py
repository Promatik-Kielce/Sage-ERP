# -*- coding: utf-8 -*-

from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    theme_preference = fields.Selection([
        ('light', 'Light Mode'),
        ('dark', 'Dark Mode'),
    ], string='Theme Preference', default='dark',
       help='Choose your preferred theme for the Odoo interface')

    @api.model
    def get_user_theme_preference(self):
        """Return the current user's theme preference"""
        return self.env.user.theme_preference or 'dark'

    @property
    def SELF_READABLE_FIELDS(self):
        """Add theme_preference to user-readable fields"""
        return super().SELF_READABLE_FIELDS + ['theme_preference']

    @property
    def SELF_WRITEABLE_FIELDS(self):
        """Add theme_preference to user-writeable fields"""
        return super().SELF_WRITEABLE_FIELDS + ['theme_preference']
