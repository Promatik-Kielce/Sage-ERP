/** @odoo-module **/

import { Component, useState, onMounted, onWillUnmount } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { rpc } from "@web/core/network/rpc";

export class KioskActionChoice extends Component {
    static template = "hr_attendance_timesheet_project.KioskActionChoice";
    static components = { Dialog };
    static props = {
        employeeId: Number,
        attendanceId: Number,
        employeeName: { type: String, optional: true },
        currentProjectName: { type: String, optional: true },
        checkInTime: { type: String, optional: true },
        inactivityTimeout: { type: Number, optional: true },
        token: { type: String, optional: true },
        mode: { type: String, optional: true },
        onCheckOut: Function,
        onProjectChanged: Function,
        onCancel: { type: Function, optional: true },
        close: Function,
    };

    setup() {
        this.state = useState({
            showProjectList: false,
            showEarlyCheckoutConfirm: false,
            projects: [],
            loading: false,
            selectedProjectId: null,
            error: null,
            closing: false,
            searchTerm: "",
            earlyCheckoutData: null,
        });

        console.log("[KioskActionChoice] Component setup with props:", this.props);
        console.log("[KioskActionChoice] effectiveMode:", this.effectiveMode);

        this.inactivityTimer = null;
        this.inactivityTimeout = this.props.inactivityTimeout || 60000;

        onMounted(() => {
            this._setupActivityListeners();
            this._startInactivityTimer();
        });

        onWillUnmount(() => {
            this._cleanupActivityListeners();
            this._clearInactivityTimer();
        });
    }

    get effectiveMode() {
        if (this.props.mode) {
            return this.props.mode;
        }
        return this.props.token ? "kiosk" : "systray";
    }

    get formattedCheckInTime() {
        if (!this.props.checkInTime) {
            return null;
        }
        const utcDate = new Date(this.props.checkInTime.replace(" ", "T") + "Z");
        const hours = String(utcDate.getHours()).padStart(2, "0");
        const minutes = String(utcDate.getMinutes()).padStart(2, "0");
        return `${hours}:${minutes}`;
    }

    get formattedPlannedEndTime() {
        if (!this.props.checkInTime) {
            return null;
        }
        const start = this._parseUtcDatetime(this.props.checkInTime);
        if (!start || isNaN(start.getTime())) {
            return null;
        }
        const plannedEnd = new Date(start.getTime() + 8 * 60 * 60 * 1000);
        const hours = String(plannedEnd.getHours()).padStart(2, "0");
        const minutes = String(plannedEnd.getMinutes()).padStart(2, "0");
        return `${hours}:${minutes}`;
    }

    get filteredProjects() {
        if (!this.state.searchTerm || !this.state.searchTerm.trim()) {
            return this.state.projects;
        }

        const searchLower = this.state.searchTerm.toLowerCase().trim();
        return this.state.projects.filter((project) => {
            const projectNumberMatch =
                project.project_number &&
                project.project_number.toLowerCase().includes(searchLower);
            const projectNameMatch =
                project.name && project.name.toLowerCase().includes(searchLower);
            const partnerNameMatch =
                project.partner_name &&
                project.partner_name.toLowerCase().includes(searchLower);
            return projectNumberMatch || projectNameMatch || partnerNameMatch;
        });
    }

    async onClickChangeProject() {
        console.log("[KioskActionChoice] Change project button clicked");

        this.state.loading = true;
        this.state.error = null;
        this.state.showProjectList = true;

        try {
            const result = await rpc("/hr_attendance/kiosk_get_employee_projects", {
                employee_id: this.props.employeeId,
            });

            console.log("[KioskActionChoice] Projects loaded:", result);

            this.state.projects = result.projects || [];

            if (this.state.projects.length === 0) {
                this.state.error = "Brak dostępnych projektów";
                console.warn("[KioskActionChoice] No projects found");
            }
        } catch (error) {
            console.error("[KioskActionChoice] Failed to load projects:", error);
            this.state.error = "Nie udało się załadować projektów. Spróbuj ponownie.";
            this.state.projects = [];
        } finally {
            this.state.loading = false;
        }
    }

    async onSelectProject(projectId) {
        console.log("[KioskActionChoice] Project selected:", projectId);

        this.state.selectedProjectId = projectId;
        this.state.loading = true;
        this.state.error = null;

        try {
            const result = await rpc("/hr_attendance/kiosk_change_project", {
                attendance_id: this.props.attendanceId,
                project_id: projectId,
            });

            console.log("[KioskActionChoice] Project change result:", result);

            if (result.success === false) {
                throw new Error(result.error || "Nie udało się zmienić projektu");
            }

            await this.props.onProjectChanged(projectId);

            this.state.closing = true;

            if (this.props.close) {
                this.props.close();
            }
        } catch (error) {
            console.error("[KioskActionChoice] Failed to change project:", error);
            this.state.error =
                error.message || "Nie udało się zmienić projektu. Spróbuj ponownie.";
            this.state.loading = false;
        }
    }

    async onClickCheckOut() {
        console.log("[KioskActionChoice] Check out button clicked");
        console.log("[KioskActionChoice] mode:", this.props.mode);
        console.log("[KioskActionChoice] token:", this.props.token);
        console.log("[KioskActionChoice] effectiveMode:", this.effectiveMode);
        console.log("[KioskActionChoice] attendanceId:", this.props.attendanceId);

        this.state.loading = true;
        this.state.error = null;

        try {
            const isSystray = this.effectiveMode === "systray";
            const route = isSystray
                ? "/hr_attendance/systray_check_early_checkout"
                : "/hr_attendance/kiosk_check_early_checkout";

            const payload = isSystray
                ? {
                    attendance_id: this.props.attendanceId,
                }
                : {
                    token: this.props.token,
                    attendance_id: this.props.attendanceId,
                };

            console.log("[KioskActionChoice] route:", route);
            console.log("[KioskActionChoice] payload:", payload);

            const result = await rpc(route, payload);

            console.log("[KioskActionChoice] Early checkout check result:", result);

            if (!result || result.success === false) {
                throw new Error(result?.error || "Nie udało się sprawdzić czasu pracy");
            }

            if (result.worked_8h) {
                await this.props.onCheckOut();
                this.state.closing = true;
                if (this.props.close) {
                    this.props.close();
                }
                return;
            }

            this.state.earlyCheckoutData = result;
            this.state.showEarlyCheckoutConfirm = true;
            this.state.loading = false;
        } catch (error) {
            console.error("[KioskActionChoice] Check out validation error:", error);
            this.state.error =
                error.message || "Nie udało się sprawdzić czasu pracy. Spróbuj ponownie.";
            this.state.loading = false;
        }
    }

    async onConfirmEarlyCheckOut() {
        console.log("[KioskActionChoice] Early check out confirmed");

        this.state.loading = true;
        this.state.error = null;

        try {
            await this.props.onCheckOut();

            this.state.closing = true;
            if (this.props.close) {
                this.props.close();
            }
        } catch (error) {
            console.error("[KioskActionChoice] Early check out error:", error);
            this.state.error =
                error.message || "Nie udało się wylogować. Spróbuj ponownie.";
            this.state.loading = false;
        }
    }

    onCancelEarlyCheckOut() {
        console.log("[KioskActionChoice] Early check out cancelled");
        this.state.showEarlyCheckoutConfirm = false;
        this.state.earlyCheckoutData = null;
        this.state.error = null;
    }

    onClickCancel() {
        console.log("[KioskActionChoice] Cancel button clicked");

        this.state.closing = true;

        if (this.props.close) {
            this.props.close();
        }

        if (this.props.onCancel) {
            this.props.onCancel();
        }
    }

    onClickBack() {
        console.log("[KioskActionChoice] Back button clicked");
        this.state.showProjectList = false;
        this.state.error = null;
        this.state.selectedProjectId = null;
        this.state.searchTerm = "";
    }

    onSearchInput(event) {
        this.state.searchTerm = event.target.value;
    }

    clearSearch() {
        this.state.searchTerm = "";
    }

    _setupActivityListeners() {
        this._handleActivity = this._handleActivity.bind(this);
        document.addEventListener("mousemove", this._handleActivity, { passive: true });
        document.addEventListener("mousedown", this._handleActivity, { passive: true });
        document.addEventListener("keydown", this._handleActivity, { passive: true });
        document.addEventListener("touchstart", this._handleActivity, { passive: true });
        document.addEventListener("click", this._handleActivity, { passive: true });
    }

    _cleanupActivityListeners() {
        if (this._handleActivity) {
            document.removeEventListener("mousemove", this._handleActivity);
            document.removeEventListener("mousedown", this._handleActivity);
            document.removeEventListener("keydown", this._handleActivity);
            document.removeEventListener("touchstart", this._handleActivity);
            document.removeEventListener("click", this._handleActivity);
        }
    }

    _handleActivity() {
        this._resetInactivityTimer();
    }

    _startInactivityTimer() {
        this._clearInactivityTimer();
        this.inactivityTimer = setTimeout(() => {
            console.log("[KioskActionChoice] Inactivity timeout, auto-cancelling");
            if (!this.state.closing) {
                this.onClickCancel();
            }
        }, this.inactivityTimeout);
    }

    _clearInactivityTimer() {
        if (this.inactivityTimer) {
            clearTimeout(this.inactivityTimer);
            this.inactivityTimer = null;
        }
    }

    _resetInactivityTimer() {
        this._startInactivityTimer();
    }

    _parseUtcDatetime(value) {
        if (!value) {
            return null;
        }
        return new Date(value.replace(" ", "T") + "Z");
    }

    _formatHourMinute(value) {
        const date = this._parseUtcDatetime(value);
        if (!date || isNaN(date.getTime())) {
            return null;
        }
        const hours = String(date.getHours()).padStart(2, "0");
        const minutes = String(date.getMinutes()).padStart(2, "0");
        return `${hours}:${minutes}`;
    }

    _formatDuration(seconds) {
        const safeSeconds = Math.max(0, Number(seconds || 0));
        const totalMinutes = Math.floor(safeSeconds / 60);
        const hours = Math.floor(totalMinutes / 60);
        const minutes = totalMinutes % 60;

        if (hours > 0 && minutes > 0) {
            return `${hours} godz. ${minutes} min.`;
        }
        if (hours > 0) {
            return `${hours} godz.`;
        }
        return `${minutes} min.`;
    }

    get earlyCheckInTime() {
        return this._formatHourMinute(this.state.earlyCheckoutData?.check_in);
    }

    get earlyPlannedEndTime() {
        return this._formatHourMinute(this.state.earlyCheckoutData?.planned_end);
    }

    get earlyRemainingTime() {
        return this._formatDuration(this.state.earlyCheckoutData?.remaining_seconds);
    }
}