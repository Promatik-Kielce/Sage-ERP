# -*- coding: utf-8 -*-

from odoo import http, _, fields
from odoo.http import request
from odoo.tools import float_round
from odoo.tools.image import image_data_uri
import datetime
import logging

_logger = logging.getLogger(__name__)


class HrAttendanceTimesheetProject(http.Controller):

    @staticmethod
    def _get_company(token):
        """Get company from kiosk token"""
        company = request.env['res.company'].sudo().search([('attendance_kiosk_key', '=', token)])
        return company

    @staticmethod
    def _get_employee_info_response(employee):
        """
        Get employee info response for kiosk checkout confirmation.

        PERFORMANCE OPTIMIZATION: This method only accesses STORED fields to avoid
        triggering expensive computed field recalculations (hours_today, total_overtime, etc.)
        which caused ~10s delays after kiosk inactivity.
        """
        response = {}
        if employee:
            # Get current attendance info from stored fields only
            current_attendance = employee.last_attendance_id
            current_project_name = None

            # Derive attendance_state from stored check_out field instead of computed field
            is_checked_in = bool(current_attendance and not current_attendance.check_out)

            if is_checked_in and current_attendance.active_timesheet_id:
                if current_attendance.active_timesheet_id.project_id:
                    current_project_name = current_attendance.active_timesheet_id.project_id.display_name

            # Return minimal data using STORED fields only - no expensive computed fields
            response = {
                'id': employee.id,
                'employee_name': employee.name,
                'employee_avatar': employee.image_256 and image_data_uri(employee.image_256),
                # Stored related field
                'last_check_in': employee.last_check_in,
                # Derived from stored field, not computed
                'attendance_state': 'checked_in' if is_checked_in else 'checked_out',
                # Stored fields from company
                'kiosk_delay': employee.company_id.attendance_kiosk_delay * 1000,
                'inactivity_timeout': employee.company_id.attendance_kiosk_inactivity_timeout * 1000,
                # Attendance data from stored fields
                'attendance': {
                    'check_in': current_attendance.check_in if current_attendance else None,
                    'check_out': current_attendance.check_out if current_attendance else None
                },
                'current_project_name': current_project_name,
                # Stored company settings
                'display_systray': employee.company_id.attendance_from_systray,
                'device_tracking_enabled': employee.company_id.attendance_device_tracking,
                'use_pin': employee.company_id.attendance_kiosk_use_pin,
                'display_overtime': employee.company_id.hr_attendance_display_overtime,
                # NOTE: These expensive computed fields are intentionally excluded:
                # - hours_today (triggers _compute_hours_today with DB search)
                # - hours_previously_today (same)
                # - last_attendance_worked_hours (same)
                # - total_overtime (triggers _read_group query)
            }
        return response

    @http.route('/hr_attendance/kiosk_check_employee_status', type='jsonrpc', auth='public')
    def kiosk_check_employee_status(self, token, barcode=None, employee_id=None):
        """
        Check employee status WITHOUT toggling attendance.
        Used to determine if we should show action choice dialog.
        """
        _logger.info("[Kiosk] check_employee_status called - barcode: %s, employee_id: %s", barcode, employee_id)
        company = self._get_company(token)
        if not company:
            _logger.warning("[Kiosk] No company found for token")
            return {}

        # Find employee by barcode or ID
        if barcode:
            employee = request.env['hr.employee'].sudo().search([
                ('barcode', '=', barcode),
                ('company_id', '=', company.id)
            ], limit=1)
        elif employee_id:
            employee = request.env['hr.employee'].sudo().browse(employee_id)
            if employee.company_id != company:
                return {}
        else:
            return {}

        if not employee:
            _logger.warning("[Kiosk] No employee found")
            return {}

        # Get current attendance info - using stored fields only to avoid expensive computed field access
        current_attendance = employee.last_attendance_id
        current_project_name = None
        attendance_id = None

        # Derive attendance_state from stored check_out field instead of computed field
        # This avoids triggering _compute_attendance_state -> _compute_last_attendance_id chain
        is_checked_in = bool(current_attendance and not current_attendance.check_out)

        if is_checked_in:
            # Employee is checked in
            attendance_id = current_attendance.id
            # Get project from active timesheet
            if current_attendance.active_timesheet_id and current_attendance.active_timesheet_id.project_id:
                current_project_name = current_attendance.active_timesheet_id.project_id.display_name

        result = {
            'employee_id': employee.id,
            'employee_name': employee.name,
            'attendance_state': 'checked_in' if is_checked_in else 'checked_out',
            'attendance_id': attendance_id,
            'current_project_name': current_project_name,
            'check_in': str(current_attendance.check_in) if is_checked_in and current_attendance.check_in else None,
            'use_pin': company.attendance_kiosk_use_pin,
        }
        _logger.info("[Kiosk] check_employee_status result: %s", result)
        return result

    @http.route('/hr_attendance/kiosk_validate_pin', type='jsonrpc', auth='public')
    def kiosk_validate_pin(self, token, employee_id, pin_code):
        """
        Validate employee PIN without performing attendance action.
        Returns whether PIN is valid.
        """
        _logger.info("[Kiosk] validate_pin called for employee: %s", employee_id)
        company = self._get_company(token)
        if not company:
            _logger.warning("[Kiosk] No company found for token")
            return {'valid': False}

        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if not employee or employee.company_id != company:
            _logger.warning("[Kiosk] Employee not found or wrong company")
            return {'valid': False}

        # Check if PIN is required
        if not company.attendance_kiosk_use_pin:
            # PIN not required - always valid
            return {'valid': True}

        # Validate PIN
        pin_valid = (employee.pin == pin_code)
        _logger.info("[Kiosk] PIN validation result: %s", pin_valid)

        return {'valid': pin_valid}

    @http.route('/hr_attendance/kiosk_get_employee_projects', type='jsonrpc', auth='public')
    def kiosk_get_employee_projects(self, employee_id):
        """
        Get list of available projects for employee to choose from.
        Returns all projects that allow timesheets.
        """
        _logger.info("[Kiosk] get_employee_projects called for employee: %s", employee_id)
        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if not employee:
            _logger.warning("[Kiosk] Employee %s not found", employee_id)
            return {'projects': []}

        # Get all projects that allow timesheets
        projects = request.env['project.project'].sudo().search([
            ('allow_timesheets', '=', True),
            ('active', '=', True),
            ('is_internal_project', '=', False),
        ])

        project_list = [{
            'id': project.id,
            'project_number': project.project_number,
            'name': project.name,
            'partner_name': project.partner_id.name if project.partner_id else '',
        } for project in projects]

        return {'projects': project_list}

    @http.route('/hr_attendance/kiosk_change_project', type='jsonrpc', auth='public')
    def kiosk_change_project(self, attendance_id, project_id):
        """
        Change project for current attendance WITHOUT checking out.
        Uses the change_project_to method from hr.attendance model.
        """
        _logger.info("[Kiosk] change_project called - attendance: %s, project: %s", attendance_id, project_id)
        attendance = request.env['hr.attendance'].sudo().browse(attendance_id)
        if not attendance or attendance.check_out:
            _logger.warning("[Kiosk] Attendance not found or already checked out")
            return {'success': False, 'error': _('Attendance not found or already checked out')}

        project = request.env['project.project'].sudo().browse(project_id)
        if not project:
            _logger.warning("[Kiosk] Project %s not found", project_id)
            return {'success': False, 'error': _('Project not found')}

        try:
            # Call the change_project_to method from our module
            attendance.change_project_to(project_id)
            _logger.info("[Kiosk] Project changed successfully to %s", project.display_name)
            return {
                'success': True,
                'project_name': project.display_name,
            }
        except Exception as e:
            _logger.error("[Kiosk] Error changing project: %s", str(e), exc_info=True)
            return {'success': False, 'error': str(e)}

    @http.route('/hr_attendance/kiosk_checkout', type='jsonrpc', auth='public')
    def kiosk_checkout(self, token, attendance_id, pin_code=None, barcode_authenticated=False, latitude=False, longitude=False):
        """
        Perform check-out for the given attendance.
        NOTE: PIN validation should be done in frontend before calling this,
        but we add defensive validation here as well.

        Args:
            barcode_authenticated: If True, skip PIN validation (barcode scan is the auth method)
        """
        _logger.info("[Kiosk] kiosk_checkout called for attendance: %s (barcode_auth: %s)", attendance_id, barcode_authenticated)
        company = self._get_company(token)
        if not company:
            _logger.warning("[Kiosk] No company found")
            return {}

        attendance = request.env['hr.attendance'].sudo().browse(attendance_id)
        if not attendance or attendance.check_out:
            _logger.warning("[Kiosk] Attendance not found or already checked out")
            return {}

        employee = attendance.employee_id

        # DEFENSIVE PIN VALIDATION (belt and suspenders approach)
        # Skip PIN validation if this was authenticated by barcode scan
        if company.attendance_kiosk_use_pin and not barcode_authenticated:
            if pin_code is None or employee.pin != pin_code:
                _logger.warning("[Kiosk] PIN validation failed in kiosk_checkout")
                return {}

        # Get geoip info
        geo_ip_response = self._get_geoip_response(
            'kiosk',
            latitude=latitude,
            longitude=longitude,
            device_tracking_enabled=company.attendance_device_tracking
        )

        # Perform check-out by calling _attendance_action_change
        employee.sudo()._attendance_action_change(geo_ip_response)

        return self._get_employee_info_response(employee)

    @http.route('/hr_attendance/kiosk_get_employee_info', type='jsonrpc', auth='public')
    def kiosk_get_employee_info(self, token, employee_id):
        """
        Get employee info after project change (for greeting screen).
        """
        company = self._get_company(token)
        if not company:
            return {}

        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if not employee or employee.company_id != company:
            return {}

        return self._get_employee_info_response(employee)

    @staticmethod
    def _get_geoip_response(mode, latitude=False, longitude=False, device_tracking_enabled=True):
        """Get geoip response - copied from hr_attendance controller"""
        response = {'mode': mode}

        if not device_tracking_enabled:
            return response

        if latitude and longitude:
            geo_obj = request.env['base.geocoder']
            location_request = geo_obj._call_openstreetmap_reverse(latitude, longitude)
            if location_request and location_request.get('display_name'):
                location = location_request.get('display_name')
            else:
                location = _('Unknown')
        else:
            city = request.geoip.city.name
            country = request.geoip.country.name
            if city and country:
                location = f"{city}, {country}"
            else:
                location = _('Unknown')

        response.update({
            'location': location,
            'latitude': latitude or request.geoip.location.latitude or False,
            'longitude': longitude or request.geoip.location.longitude or False,
            'ip_address': request.geoip.ip,
            'browser': request.httprequest.user_agent.browser,
        })

        return response

    @http.route('/hr_attendance/kiosk_check_early_checkout', type='jsonrpc', auth='public')
    def kiosk_check_early_checkout(self, token, attendance_id):
        """
        Check whether employee has worked at least 8 hours.
        Returns data for early checkout warning dialog.
        """
        company = self._get_company(token)
        if not company:
            return {'success': False, 'error': _('No company found')}

        attendance = request.env['hr.attendance'].sudo().browse(attendance_id)
        if not attendance.exists() or attendance.check_out:
            return {'success': False, 'error': _('Attendance not found or already checked out')}

        employee = attendance.employee_id
        if employee.company_id != company:
            return {'success': False, 'error': _('Invalid employee/company')}

        check_in = attendance.check_in
        if not check_in:
            return {'success': False, 'error': _('Missing check-in time')}

        now = fields.Datetime.now()
        planned_end = check_in + datetime.timedelta(hours=8)
        remaining_seconds = int((planned_end - now).total_seconds())

        return {
            'success': True,
            'worked_8h': now >= planned_end,
            'check_in': fields.Datetime.to_string(check_in),
            'planned_end': fields.Datetime.to_string(planned_end),
            'remaining_seconds': max(0, remaining_seconds),
        }

    @http.route('/hr_attendance/systray_check_early_checkout', type='jsonrpc', auth='user')
    def systray_check_early_checkout(self, attendance_id):
        try:
            _logger.warning("[Kiosk] systray_check_early_checkout attendance_id=%s user=%s", attendance_id,
                            request.env.user.id)

            attendance = request.env['hr.attendance'].sudo().browse(attendance_id)
            if not attendance.exists() or attendance.check_out:
                return {'success': False, 'error': _('Attendance not found or already checked out')}

            employee = attendance.employee_id
            user_employee = request.env.user.employee_id

            if not user_employee or user_employee != employee:
                return {'success': False, 'error': _('You are not allowed to access this attendance')}

            check_in = attendance.check_in
            if not check_in:
                return {'success': False, 'error': _('Missing check-in time')}

            now = fields.Datetime.now()
            planned_end = check_in + datetime.timedelta(hours=8)
            remaining_seconds = int((planned_end - now).total_seconds())

            return {
                'success': True,
                'worked_8h': now >= planned_end,
                'check_in': fields.Datetime.to_string(check_in),
                'planned_end': fields.Datetime.to_string(planned_end),
                'remaining_seconds': max(0, remaining_seconds),
            }
        except Exception as e:
            _logger.exception("[Kiosk] systray_check_early_checkout failed")
            raise