# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import re
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Automatically split existing project names like '123 - Project Name'
    into separate project_number and name fields.
    """
    _logger.info("Starting project number migration...")

    # Pattern matches: "123 - Name", "PRJ-001 - Name", "A1.2 - Name"
    # Supports alphanumeric with dots, dashes, and slashes
    pattern = r'^([A-Za-z0-9]+(?:[.\-/][A-Za-z0-9]+)*)\s*[-–—]\s*(.+)$'

    # Get all projects
    cr.execute("""
        SELECT id, name
        FROM project_project
        WHERE project_number IS NULL OR project_number = ''
    """)

    projects = cr.fetchall()
    migrated = 0
    failed = []

    for project_id, current_name in projects:
        if not current_name:
            failed.append((project_id, 'EMPTY', 'empty_name'))
            continue

        match = re.match(pattern, current_name.strip())

        if match:
            number = match.group(1).strip()
            new_name = match.group(2).strip()

            # Check if this number already exists
            cr.execute("""
                SELECT id, name FROM project_project
                WHERE project_number = %s AND id != %s
                LIMIT 1
            """, (number, project_id))

            existing = cr.fetchone()

            if existing:
                # Number collision - generate unique number
                suffix = 2
                unique_number = f"{number}-DUP-{suffix}"
                while True:
                    cr.execute("""
                        SELECT id FROM project_project
                        WHERE project_number = %s
                    """, (unique_number,))
                    if not cr.fetchone():
                        break
                    suffix += 1
                    unique_number = f"{number}-DUP-{suffix}"

                cr.execute("""
                    UPDATE project_project
                    SET project_number = %s, name = %s
                    WHERE id = %s
                """, (unique_number, new_name, project_id))

                failed.append((project_id, current_name, f'duplicate_{number}'))
                _logger.warning(
                    "Project ID %s: Duplicate number '%s' detected. "
                    "Assigned '%s' instead.",
                    project_id, number, unique_number
                )
            else:
                # Success - update with extracted values
                cr.execute("""
                    UPDATE project_project
                    SET project_number = %s, name = %s
                    WHERE id = %s
                """, (number, new_name, project_id))
                migrated += 1
        else:
            # No pattern match - generate temp number
            temp_number = f"TEMP-{project_id}"
            cr.execute("""
                UPDATE project_project
                SET project_number = %s
                WHERE id = %s
            """, (temp_number, project_id))
            failed.append((project_id, current_name, 'no_pattern'))
            _logger.warning(
                "Project ID %s ('%s'): No number pattern found. "
                "Assigned temporary number '%s'.",
                project_id, current_name, temp_number
            )

    _logger.info(
        "Migration complete: %s projects migrated successfully, "
        "%s require manual attention.",
        migrated, len(failed)
    )

    if failed:
        _logger.warning(
            "Projects requiring manual number assignment: %s",
            ', '.join(str(p[0]) for p in failed)
        )
