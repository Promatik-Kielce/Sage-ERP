import re
from odoo import api, fields, models
from odoo.exceptions import UserError


class ProjectTaskSpecification(models.Model):
    _name = "project.task.specification"
    _description = "Project Task Specification"
    _order = "sequence, id desc"
    _rec_name = "name"

    name = fields.Char(string="Tytuł", required=True)
    project_id = fields.Many2one("project.project", string="Projekt", required=True, ondelete="cascade", index=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    state = fields.Selection(
        [("draft", "Nowa"), ("in_progress", "W trakcie"), ("approved", "Zatwierdzona"), ("archived", "Archiwalna")],
        string="Status",
        default="draft",
    )
    owner_id = fields.Many2one("res.users", string="Właściciel", default=lambda self: self.env.user)
    color = fields.Integer(string="Kolor")

    # --- TEXT SPEC ---
    description = fields.Html(string="Opis / Założenia projektowe")
    assumptions = fields.Text(string="Założenia")
    scope_in = fields.Text(string="Zakres (IN)")
    scope_out = fields.Text(string="Zakres (OUT)")
    constraints = fields.Text(string="Ograniczenia")
    acceptance_criteria = fields.Text(string="Kryteria akceptacji")
    notes = fields.Text(string="Uwagi")

    assumptions_preview = fields.Char(string="Założenia (podgląd)", compute="_compute_previews", store=False)
    description_preview = fields.Char(string="Opis (podgląd)", compute="_compute_previews", store=False)
    description_preview_html = fields.Html(string="Opis (podgląd HTML)", compute="_compute_previews", store=False)
    # --- PDF SPEC ---
    is_pdf = fields.Boolean(string="Kafelek PDF", default=False, index=True)
    pdf_file = fields.Binary(string="Plik PDF", attachment=True)
    pdf_filename = fields.Char(string="Nazwa pliku")
    pdf_uploaded_at = fields.Datetime(string="Wgrano", readonly=True)

    @api.depends("assumptions", "description")
    def _compute_previews(self):
        for rec in self:
            ass = (rec.assumptions or "").strip()
            rec.assumptions_preview = (ass[:160] + "…") if len(ass) > 160 else ass

            # tekstowe preview (jeśli nadal używasz)
            desc = (rec.description or "").strip()
            desc_txt = re.sub(r"<[^>]+>", " ", desc)
            desc_txt = re.sub(r"\s+", " ", desc_txt).strip()
            rec.description_preview = (desc_txt[:160] + "…") if len(desc_txt) > 160 else desc_txt

            # HTML preview (zachowuje listy)
            html = (rec.description or "").strip()
            rec.description_preview_html = html[:1000] if html else False

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec, vals in zip(recs, vals_list):
            if vals.get("pdf_file"):
                rec.pdf_uploaded_at = fields.Datetime.now()
                # jeśli ktoś nie podał nazwy kafelka, a mamy filename -> ustaw
                if not vals.get("name") and vals.get("pdf_filename"):
                    rec.name = vals["pdf_filename"]
        return recs

    def write(self, vals):
        res = super().write(vals)
        if "pdf_file" in vals:
            for rec in self:
                rec.pdf_uploaded_at = fields.Datetime.now() if rec.pdf_file else False
                if rec.is_pdf and vals.get("pdf_filename") and (not rec.name or rec.name == rec.pdf_filename):
                    # opcjonalnie: możesz nie nadpisywać name
                    pass
        return res

    def _pdf_content_url(self, download=False):
        self.ensure_one()
        if not self.pdf_file:
            raise UserError("Brak pliku PDF w tym kafelku.")
        # /web/content?model=...&id=...&field=...&filename_field=...&download=...
        return (
            f"/web/content?model={self._name}"
            f"&id={self.id}"
            f"&field=pdf_file"
            f"&filename_field=pdf_filename"
            f"&download={'1' if download else '0'}"
        )

    def action_preview_pdf(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": self._pdf_content_url(download=False), "target": "new"}

    def action_download_pdf(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": self._pdf_content_url(download=True), "target": "self"}