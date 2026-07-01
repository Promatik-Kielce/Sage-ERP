# Part of Odoo. See LICENSE file for full copyright and licensing details.
from odoo import fields, http
from odoo.http import request
from odoo.tools.image import image_data_uri


class FleetKioskRental(http.Controller):
    """Public kiosk endpoints for the car rental flow.

    These mirror the hr_attendance kiosk token mechanism but never touch
    attendance records. Every write goes through sudo() after re-validating
    the company token, the employee, and the car availability.
    """

    @staticmethod
    def _get_company(token):
        return request.env['res.company'].sudo().search(
            [('attendance_kiosk_key', '=', token)], limit=1)

    @staticmethod
    def _get_employee(company, employee_id):
        if not company or not employee_id:
            return request.env['hr.employee']
        employee = request.env['hr.employee'].sudo().browse(int(employee_id))
        if not employee.exists() or employee.company_id != company:
            return request.env['hr.employee']
        return employee

    def _employee_info(self, employee):
        return {
            'employee_id': employee.id,
            'employee_name': employee.name,
            'employee_avatar': employee.image_256 and image_data_uri(employee.image_256),
        }

    def _identify_payload(self, employee, company):
        """Full payload after a successful identification: employee info, whether
        they already have a car out, and the list of rentable cars."""
        payload = self._employee_info(employee)
        rental = request.env['fleet.vehicle.log.services'].sudo()._get_employee_open_rental(employee)
        payload['has_active_rental'] = bool(rental)
        payload['active_vehicle_name'] = rental.vehicle_id.display_name if rental else False
        cars = request.env['fleet.vehicle'].sudo().search([
            ('vehicle_type', '=', 'car'),
            ('company_id', 'in', (False, company.id)),
        ])
        payload['vehicles'] = cars._kiosk_rental_data()
        return payload

    @http.route('/fleet_kiosk_rental/employee_data', type='jsonrpc', auth='public')
    def employee_data(self, token, employee_id):
        """Lightweight lookup used by the manual-selection path to decide whether
        a PIN is required before identifying."""
        company = self._get_company(token)
        employee = self._get_employee(company, employee_id)
        if not employee:
            return {}
        info = self._employee_info(employee)
        info['use_pin'] = company.attendance_kiosk_use_pin
        return info

    @http.route('/fleet_kiosk_rental/identify_badge', type='jsonrpc', auth='public')
    def identify_badge(self, token, barcode):
        company = self._get_company(token)
        if not company:
            return {}
        employee = request.env['hr.employee'].sudo().search([
            ('barcode', '=', barcode),
            ('company_id', '=', company.id),
        ], limit=1)
        if not employee:
            return {}
        return self._identify_payload(employee, company)

    @http.route('/fleet_kiosk_rental/identify_pin', type='jsonrpc', auth='public')
    def identify_pin(self, token, employee_id, pin_code=False):
        company = self._get_company(token)
        employee = self._get_employee(company, employee_id)
        if not employee:
            return {}
        if company.attendance_kiosk_use_pin and employee.pin != pin_code:
            return {'error': 'wrong_pin'}
        return self._identify_payload(employee, company)

    @http.route('/fleet_kiosk_rental/rent', type='jsonrpc', auth='public')
    def rent(self, token, employee_id, vehicle_id, project_numbers=None, notes=False):
        company = self._get_company(token)
        employee = self._get_employee(company, employee_id)
        if not employee:
            return {}
        vehicle = request.env['fleet.vehicle'].sudo().browse(int(vehicle_id))
        if not vehicle.exists() or vehicle.company_id and vehicle.company_id != company:
            return {'error': 'unavailable'}

        Service = request.env['fleet.vehicle.log.services'].sudo()
        # Re-validate everything server-side (kiosk is public/untrusted).
        if Service._get_employee_open_rental(employee):
            return {'error': 'already_renting'}
        if vehicle._get_open_rental():
            return {'error': 'unavailable'}
        if vehicle.rental_state == 'service':
            return {'error': 'unavailable'}
        today = fields.Date.context_today(vehicle)
        if (vehicle.insurance_expiry_date and vehicle.insurance_expiry_date < today) or \
           (vehicle.next_technical_checkup_date and vehicle.next_technical_checkup_date < today):
            return {'error': 'unavailable'}

        project_numbers = [
            p.strip() for p in (project_numbers or []) if p and p.strip()
        ]
        vals = {
            'vehicle_id': vehicle.id,
            'is_rental': True,
            'employee_id': employee.id,
            'rental_start': fields.Datetime.now(),
            'date': today,
            'state': 'running',
            'notes': notes or False,
            'project_number_ids': [(0, 0, {'name': p}) for p in project_numbers],
        }
        service_type = request.env.ref(
            'fleet_kiosk_rental.fleet_service_type_car_rental', raise_if_not_found=False)
        if service_type:
            vals['service_type_id'] = service_type.id
        Service.create(vals)
        vehicle.rental_state = 'delegation'
        return {'success': True, 'vehicle_name': vehicle.display_name}

    @http.route('/fleet_kiosk_rental/return_car', type='jsonrpc', auth='public')
    def return_car(self, token, employee_id):
        company = self._get_company(token)
        employee = self._get_employee(company, employee_id)
        if not employee:
            return {}
        rental = request.env['fleet.vehicle.log.services'].sudo()._get_employee_open_rental(employee)
        if not rental:
            return {'error': 'no_rental'}
        rental.write({
            'rental_return': fields.Datetime.now(),
            'state': 'done',
        })
        rental.vehicle_id.rental_state = 'parking'
        return {'success': True, 'vehicle_name': rental.vehicle_id.display_name}
