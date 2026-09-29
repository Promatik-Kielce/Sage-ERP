def post_init_hook(env):
    # Managers assigned before this module was installed also need the officer group.
    env["hr.employee.manager.rel"].search([])._grant_attendance_officer_group()
