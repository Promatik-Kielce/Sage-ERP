# Project Number Extension

Adds a dedicated project number field to Odoo projects with global uniqueness validation.

## Overview

This module enhances the Odoo project management system by separating project numbers from project names. Previously, projects were identified by a single name field containing both number and name (e.g., "123 - Automotive assembly line"). This module creates a dedicated `project_number` field with proper validation and constraints.

## Features

- **Separate `project_number` field**: Required field, distinct from project name
- **Global uniqueness**: Project numbers are unique across all projects and companies
- **Permanent reservation**: Archived projects retain their numbers (no reuse)
- **Display format**: Projects automatically display as "PROJECT_NUMBER - Project Name"
- **Smart search**: Search projects by either number or name
- **Change tracking**: Project number changes are tracked in the chatter
- **Automatic migration**: Existing projects are automatically processed during installation

## Installation

1. Copy the `project_number_extension` module to your Odoo `addons/` directory
2. Restart the Odoo server
3. Go to **Apps** menu
4. Click **Update Apps List**
5. Search for "Project Number Extension"
6. Click **Install**

## Migration Behavior

When the module is installed, the migration script automatically processes existing projects:

### Automatic Splitting

Projects with names in the format "NUMBER - NAME" are automatically split:
- **Input**: "123 - Automotive assembly line"
- **Result**:
  - project_number: "123"
  - name: "Automotive assembly line"
  - display: "123 - Automotive assembly line"

### Supported Number Formats

The migration script recognizes various numbering patterns:
- Simple numbers: `123 - Project Name`
- Alphanumeric: `PRJ-001 - Project Name`
- With dots: `A1.2 - Project Name`
- With slashes: `2024/001 - Project Name`

### Duplicate Handling

If multiple projects have the same number:
- First project keeps the original number
- Subsequent projects get suffixed numbers: `123-DUP-2`, `123-DUP-3`, etc.
- All duplicates are logged for manual review

### Temporary Numbers

Projects without the "NUMBER - NAME" pattern receive temporary numbers:
- Format: `TEMP-{project_id}`
- Example: `TEMP-42`
- These should be manually updated after installation

### Migration Logs

Check the Odoo server logs after installation:
```
INFO: Migration complete: 45 projects migrated successfully, 3 require manual attention.
WARNING: Projects requiring manual number assignment: 12, 23, 34
```

## Usage

### Creating New Projects

When creating a new project:

1. **Project Number** (required): Enter a unique identifier
   - Examples: `PRJ-001`, `2024-15`, `AUTO-123`
   - Must be unique globally

2. **Name** (required): Enter the descriptive project name
   - Example: `Automotive assembly line`

3. **Display**: The project will automatically display as:
   - `PRJ-001 - Automotive assembly line`

### Editing Projects

- Project numbers can be changed (tracked in chatter)
- Changing to an existing number will show an error
- Project numbers cannot be empty or whitespace-only

### Copying Projects

When duplicating a project:
- The project number is **not copied** (prevents duplicates)
- You must enter a new unique number for the copy
- The project name is copied as usual

### Searching

Search for projects using either:
- Project number: Search for "123" finds "123 - Automotive assembly line"
- Project name: Search for "automotive" finds "123 - Automotive assembly line"

## Technical Details

### Model Extension

Extends: `project.project`

New field: `project_number`
- Type: Char
- Required: True
- Copy: False
- Indexed: btree_not_null
- Tracked: True

### Constraints

**Database Level (UniqueIndex)**:
```sql
UNIQUE (project_number)
```

**Python Level**:
- Uniqueness validation with user-friendly error messages
- Whitespace validation

### Display Name Override

The `display_name` computed field automatically combines:
```python
display_name = f"{project_number} - {name}"
```

### Security

Inherits access rules from base `project.project` model:
- Project Users: Read, Write, Create
- Project Managers: Read, Write, Create, Delete

## Troubleshooting

### "Project number already exists" error

**Cause**: Attempting to use a number that's already assigned to another project (including archived projects).

**Solution**: Choose a different number or update/remove the conflicting project.

### Projects with TEMP-XXX numbers

**Cause**: Project names didn't match the expected "NUMBER - NAME" format during migration.

**Solution**: Manually update these projects with proper numbers.

### Migration issues

**Check logs**: Server logs contain detailed migration information.

**Manual fix**: If needed, update projects directly:
```sql
UPDATE project_project
SET project_number = 'NEW-NUMBER', name = 'New Name'
WHERE id = XX;
```

## Uninstallation

If you need to uninstall the module:

1. The module can be safely uninstalled via the Apps menu
2. The `project_number` field will be removed from the database
3. The original `name` field remains unchanged
4. No data is lost (names were updated but not replaced)
5. Projects will display using the default `name` field

**Note**: Before uninstalling, consider backing up project numbers if you may need them later.

## Support

For issues, questions, or feature requests related to this module, please contact your Odoo administrator or consult the Sage-ERP development team.

## Version History

### 19.0.1.0.0
- Initial release
- Separate project_number field
- Global uniqueness validation
- Automatic migration script
- Display name computation
- Search integration

## License

LGPL-3
