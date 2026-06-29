# Part of Odoo. See LICENSE file for full copyright and licensing details.
{
    'name': 'Fleet Kiosk Rental',
    'version': '1.0',
    'category': 'Human Resources/Fleet',
    'summary': 'Self-service car renting from the attendance kiosk',
    'description': """
Fleet Kiosk Rental
==================
Lets employees rent (take) and return fleet cars from the attendance kiosk.

* Adds insurance expiry and next technical checkup dates to vehicles.
* Adds a Parking / Delegation / Service status used as the vehicle kanban pipeline.
* Adds a car button to the kiosk that identifies the employee (badge or PIN),
  lets them pick an available car, record project numbers and notes, and
  automatically registers the return on the next visit.
* Stores the rental history on the fleet "Services" log (shown as "Rental History").
    """,
    'author': 'Sage-ERP',
    'depends': ['fleet', 'hr_attendance', 'hr'],
    'data': [
        'security/ir.model.access.csv',
        'data/fleet_service_type_data.xml',
        'views/fleet_vehicle_views.xml',
        'views/fleet_vehicle_log_services_views.xml',
    ],
    'assets': {
        'hr_attendance.assets_public_attendance': [
            'fleet_kiosk_rental/static/src/scss/kiosk_rental.scss',
            'fleet_kiosk_rental/static/src/js/kiosk_rental.js',
            'fleet_kiosk_rental/static/src/xml/kiosk_rental.xml',
        ],
    },
    'license': 'LGPL-3',
}
