/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useState } from "@odoo/owl";
import { useBus } from "@web/core/utils/hooks";
import { rpc } from "@web/core/network/rpc";
import { _t } from "@web/core/l10n/translation";
import { browser } from "@web/core/browser/browser";
import { KioskPinCode } from "@hr_attendance/components/pin_code/pin_code";
import publicKioskApp from "@hr_attendance/public_kiosk/public_kiosk_app";

const { kioskAttendanceApp } = publicKioskApp;

/**
 * PIN pad reused for the car rental flow. Same keypad behaviour as the
 * attendance one, but with a rental-specific heading template.
 */
export class CarRentalPinCode extends KioskPinCode {
    static template = "fleet_kiosk_rental.CarRentalPinConfirm";
}

const CAR_DISPLAYS = ["car_auth", "car_manual", "car_pin", "car_list", "car_form", "car_done"];

// Register the rental PIN component so the inherited template can use it.
kioskAttendanceApp.components = {
    ...kioskAttendanceApp.components,
    CarRentalPinCode,
};

patch(kioskAttendanceApp.prototype, {
    setup() {
        super.setup();
        this.carRental = useState({
            employee: null,
            pinEmployee: null,
            vehicles: [],
            selectedVehicleId: null,
            selectedVehicleName: "",
            projectNumbers: [""],
            notes: "",
            confirmation: null,
        });
        // Always listen for badge scans so the rental flow works even in
        // manual-only kiosk mode (where the base app does not subscribe).
        useBus(this.barcode.bus, "barcode_scanned", (ev) =>
            this.onCarBarcodeScanned(ev.detail.barcode)
        );
    },

    switchDisplay(screen) {
        if (CAR_DISPLAYS.includes(screen)) {
            this.state.active_display = screen;
            this._startInactivityTimer();
            return;
        }
        super.switchDisplay(screen);
    },

    /** Entry point: opened from the car button in the kiosk header. */
    openCarRental() {
        Object.assign(this.carRental, {
            employee: null,
            pinEmployee: null,
            vehicles: [],
            selectedVehicleId: null,
            selectedVehicleName: "",
            projectNumbers: [""],
            notes: "",
            confirmation: null,
        });
        this.switchDisplay("car_auth");
    },

    async onCarBarcodeScanned(barcode) {
        if (this.lockScanner || this.state.active_display !== "car_auth") {
            return;
        }
        this.lockScanner = true;
        this.ui.block();
        try {
            const result = await rpc("/fleet_kiosk_rental/identify_badge", {
                token: this.props.token,
                barcode: barcode,
            });
            if (!result || !result.employee_id) {
                this.displayNotification(
                    _t("No employee corresponding to Badge ID '%(barcode)s.'", { barcode })
                );
                return;
            }
            await this._afterCarIdentify(result);
        } catch (error) {
            this.displayNotification(error.data ? error.data.message : error.message);
        } finally {
            this.lockScanner = false;
            this.ui.unblock();
        }
    },

    /** Manual selection -> decide whether a PIN is required. */
    async carConfirm(employeeId) {
        const emp = await rpc("/fleet_kiosk_rental/employee_data", {
            token: this.props.token,
            employee_id: employeeId,
        });
        if (!emp || !emp.employee_id) {
            this.displayNotification(_t("Could not find the selected employee."));
            return;
        }
        if (emp.use_pin) {
            this.carRental.pinEmployee = {
                id: emp.employee_id,
                employee_name: emp.employee_name,
                employee_avatar: emp.employee_avatar,
            };
            this.switchDisplay("car_pin");
        } else {
            await this.carPinConfirm(employeeId, false);
        }
    },

    async carPinConfirm(employeeId, pin) {
        this.ui.block();
        try {
            const result = await rpc("/fleet_kiosk_rental/identify_pin", {
                token: this.props.token,
                employee_id: employeeId,
                pin_code: pin,
            });
            if (result && result.error === "wrong_pin") {
                this.displayNotification(_t("Wrong PIN"));
                return;
            }
            await this._afterCarIdentify(result);
        } finally {
            this.ui.unblock();
        }
    },

    async _afterCarIdentify(payload) {
        if (!payload || !payload.employee_id) {
            this.displayNotification(_t("Employee not recognized."));
            return;
        }
        this.carRental.employee = payload;
        if (payload.has_active_rental) {
            // Coming back: register the return automatically.
            const result = await rpc("/fleet_kiosk_rental/return_car", {
                token: this.props.token,
                employee_id: payload.employee_id,
            });
            if (result && result.success) {
                this.carRental.confirmation = {
                    mode: "returned",
                    vehicleName: result.vehicle_name,
                };
                this._showCarDone();
            } else {
                this.displayNotification(_t("Could not register the car return."));
            }
        } else {
            this.carRental.vehicles = payload.vehicles || [];
            this.switchDisplay("car_list");
        }
    },

    selectCar(vehicle) {
        if (!vehicle.available) {
            return;
        }
        this.carRental.selectedVehicleId = vehicle.id;
        this.carRental.selectedVehicleName = vehicle.name;
        this.carRental.projectNumbers = [""];
        this.carRental.notes = "";
        this.switchDisplay("car_form");
    },

    addProjectNumber() {
        this.carRental.projectNumbers.push("");
    },

    removeProjectNumber(index) {
        if (this.carRental.projectNumbers.length > 1) {
            this.carRental.projectNumbers.splice(index, 1);
        } else {
            this.carRental.projectNumbers[0] = "";
        }
    },

    updateProjectNumber(index, value) {
        this.carRental.projectNumbers[index] = value;
    },

    async confirmRent() {
        const projectNumbers = this.carRental.projectNumbers
            .map((p) => (p || "").trim())
            .filter((p) => p);
        this.ui.block();
        try {
            const result = await rpc("/fleet_kiosk_rental/rent", {
                token: this.props.token,
                employee_id: this.carRental.employee.employee_id,
                vehicle_id: this.carRental.selectedVehicleId,
                project_numbers: projectNumbers,
                notes: this.carRental.notes || false,
            });
            if (result && result.success) {
                this.carRental.confirmation = {
                    mode: "rented",
                    vehicleName: result.vehicle_name,
                };
                this._showCarDone();
            } else {
                this.displayNotification(
                    _t("Could not rent this car. It may no longer be available.")
                );
                this.switchDisplay("car_list");
            }
        } finally {
            this.ui.unblock();
        }
    },

    _showCarDone() {
        this.switchDisplay("car_done");
        browser.clearTimeout(this._carDoneTimer);
        this._carDoneTimer = browser.setTimeout(() => {
            if (this.state.active_display === "car_done") {
                this.kioskReturn();
            }
        }, 5000);
    },
});
