# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class DiscussGifFavorite(models.Model):
    _name = 'discuss.gif.favorite'
    _description = "Save favorite GIF from KLIPY API"

    klipy_gif_slug = fields.Char("GIF slug from KLIPY", required=True)

    _user_gif_favorite = models.Constraint(
        'unique(create_uid,klipy_gif_slug)',
        'User should not have duplicated favorite GIF',
    )
