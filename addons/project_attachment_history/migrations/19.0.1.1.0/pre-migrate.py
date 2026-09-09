# Part of Odoo. See LICENSE file for full copyright and licensing details.


def migrate(cr, version):
    """ Give the `moved` action a direction.

    Replaying a point in time needs to know whether a file left the record or
    arrived on it, so `moved` was split into `moved_in` / `moved_out`. Rows
    written before the split were always logged on the record the file left.
    """
    cr.execute("""
        UPDATE project_attachment_log
           SET action = 'moved_out'
         WHERE action = 'moved'
    """)
