/** @odoo-module **/

import { Component, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

console.log("[project_task_specification] loaded");

const BTN_CLASS = "o_project_task_specification_button";
const ADD_PDF_BTN_CLASS = "o_project_spec_add_pdf";

/**
 * /odoo/project/4/tasks
 */
function isProjectTasksPage() {
    const path = window.location.pathname || "";
    return /\/odoo\/project\/\d+\/tasks(?:\/.*)?$/.test(path);
}

function getProjectIdFromPath() {
    const path = window.location.pathname || "";
    const match = path.match(/\/odoo\/project\/(\d+)\/tasks(?:\/.*)?$/);
    return match ? parseInt(match[1], 10) : null;
}

function findSliderButton() {
    const nav = document.querySelector(".o_control_panel_navigation");
    if (!nav) return null;

    const candidates = nav.querySelectorAll("button.btn.btn-secondary");
    for (const btn of candidates) {
        if (btn.querySelector("i.fa.fa-sliders")) return btn;
    }
    return null;
}

/**
 * Tworzy (i wstawia) przycisk: Specyfikacja Projektowa
 * (widoczny dla wszystkich - bo wszyscy mają read)
 */
function mountSpecificationButton(actionService, nav, sliderBtn) {
    if (nav.querySelector(`.${BTN_CLASS}`)) return;

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `btn btn-secondary ${BTN_CLASS}`;
    btn.textContent = "Specyfikacja Projektowa";
    btn.title = "Otwórz specyfikację projektową";

    btn.addEventListener("click", async () => {
        const projectId = getProjectIdFromPath();
        if (!projectId) return;

        await actionService.doAction("project_task_specification.action_project_task_specification", {
            additionalContext: { default_project_id: projectId },
            domain: [["project_id", "=", projectId]],
        });
    });

    // po lewej stronie suwaków
    nav.insertBefore(btn, sliderBtn);
}

/**
 * Tworzy (i wstawia) przycisk: Add .pdf
 * (widoczny tylko dla Administratora i grupy PDF Manager)
 */
function mountAddPdfButton(actionService, nav, specBtn, canManagePdf) {
    if (!canManagePdf) {
        // jeśli nie ma uprawnień - usuń przycisk jeśli istnieje
        const existing = nav.querySelector(`.${ADD_PDF_BTN_CLASS}`);
        if (existing) existing.remove();
        return;
    }

    if (nav.querySelector(`.${ADD_PDF_BTN_CLASS}`)) return;

    const addPdfBtn = document.createElement("button");
    addPdfBtn.type = "button";
    addPdfBtn.className = `btn btn-primary ${ADD_PDF_BTN_CLASS}`;
    addPdfBtn.textContent = "Add .pdf";
    addPdfBtn.title = "Dodaj kafelek PDF do specyfikacji projektu";

    addPdfBtn.addEventListener("click", async () => {
        const projectId = getProjectIdFromPath();
        if (!projectId) return;

        await actionService.doAction("project_task_specification.action_project_task_specification", {
            additionalContext: {
                default_project_id: projectId,
                default_is_pdf: true,
                default_name: "Nowy PDF",
            },
            domain: [["project_id", "=", projectId]],
            views: [[false, "form"]],
            target: "current",
        });
    });

    // wstaw po lewej stronie przycisku "Specyfikacja Projektowa"
    // (jeśli nie ma, to na początek nawigacji)
    if (specBtn && specBtn.parentNode === nav) {
        nav.insertBefore(addPdfBtn, specBtn);
    } else {
        nav.prepend(addPdfBtn);
    }
}

class Injector extends Component {
    static template = "project_task_specification.Empty";

    setup() {
        this.action = useService("action");
        this.orm = useService("orm");
        //this.user = useService("user"); // w wielu buildach istnieje, ale nie opieramy się tylko na tym
        this._observer = null;

        // cache uprawnień, żeby nie robić RPC w pętli
        this._canManagePdf = null;
        this._permCheckPromise = null;

        const checkPermissionsOnce = async () => {
            if (this._canManagePdf !== null) return this._canManagePdf;
            if (this._permCheckPromise) return this._permCheckPromise;

            this._permCheckPromise = (async () => {
                try {
                    // 1) jeśli user-service ma hasGroup, użyj go (szybciej)
                    if (this.user && typeof this.user.hasGroup === "function") {
                        const isManager = await this.user.hasGroup(
                            "project_task_specification.group_project_spec_pdf_manager"
                        );
                        const isAdmin = await this.user.hasGroup("base.group_system");
                        this._canManagePdf = Boolean(isManager || isAdmin);
                        return this._canManagePdf;
                    }

                    // 2) fallback: RPC do res.users/has_group
                    const isManager = await this.orm.call("res.users", "has_group", [
                        "project_task_specification.group_project_spec_pdf_manager",
                    ]);
                    const isAdmin = await this.orm.call("res.users", "has_group", ["base.group_system"]);
                    this._canManagePdf = Boolean(isManager || isAdmin);
                    return this._canManagePdf;
                } catch (e) {
                    console.warn("[project_task_specification] Permission check failed:", e);
                    this._canManagePdf = false;
                    return false;
                } finally {
                    this._permCheckPromise = null;
                }
            })();

            return this._permCheckPromise;
        };

        const rerender = async () => {
            if (!isProjectTasksPage()) return;

            const sliderBtn = findSliderButton();
            if (!sliderBtn) return;

            const nav = sliderBtn.closest(".o_control_panel_navigation");
            if (!nav) return;

            // Spec button (dla wszystkich)
            mountSpecificationButton(this.action, nav, sliderBtn);

            // PDF button (tylko upoważnieni)
            const canManagePdf = await checkPermissionsOnce();
            const specBtn = nav.querySelector(`.${BTN_CLASS}`);
            mountAddPdfButton(this.action, nav, specBtn, canManagePdf);
        };

        onMounted(() => {
            setTimeout(() => rerender(), 200);
            setTimeout(() => rerender(), 800);

            this._observer = new MutationObserver(() => {
                // nie await w observerze - odpal asynchronicznie
                rerender();
            });
            this._observer.observe(document.body, { childList: true, subtree: true });
        });

        onWillUnmount(() => {
            if (this._observer) this._observer.disconnect();
        });
    }
}

registry.category("main_components").add("project_task_specification.injector", {
    Component: Injector,
});