# Part of Odoo. See LICENSE file for full copyright and licensing details.


def migrate(cr, version):
    """Migrate from Tenor GIF API to KLIPY GIF API.

    - Clear existing favorites (Tenor IDs are incompatible with KLIPY slugs)
    - Rename the tenor_gif_id column to klipy_gif_slug
    - Migrate the config parameter key
    """
    # Clear existing favorites - Tenor GIF IDs cannot be mapped to KLIPY slugs
    cr.execute("DELETE FROM discuss_gif_favorite")

    # Rename the favorites column from tenor_gif_id to klipy_gif_slug
    cr.execute("""
        ALTER TABLE discuss_gif_favorite
        RENAME COLUMN tenor_gif_id TO klipy_gif_slug
    """)

    # Migrate the config parameter key from Tenor to KLIPY
    cr.execute("""
        UPDATE ir_config_parameter
        SET key = 'discuss.klipy_api_key'
        WHERE key = 'discuss.tenor_api_key'
    """)
