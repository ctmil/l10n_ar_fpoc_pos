# -*- coding: utf-8 -*-
# TODO: vat_rate
from openerp.osv import fields, osv
from openerp.tools.translate import _
from openerp.addons.l10n_ar_fpoc.invoice import \
    document_type_map, responsability_map


class pos_config(osv.osv):
    _inherit = 'pos.config'

    _columns = {
        'fpoc_close_report': fields.selection(
            [('z_report', 'Z Report'), ('x_report', 'X Report')],
            "Report to Generate at Close"
        )
    }
pos_config()


class pos_session(osv.osv):
    _inherit = 'pos.session'

    def wkf_action_open(self, cr, uid, ids, context=None):
        r = super(pos_session, self).wkf_action_open(
            cr, uid, ids, context=context)
        # Apertura de caja.
        for sess in [s for s in self.browse(cr, uid, ids)
                     if s.config_id.journal_id.use_fiscal_printer and
                     s.config_id.journal_id.fiscal_printer_id]:
            jou = sess.config_id.journal_id
            if jou.fiscal_printer_state not in ['ready']:
                jou.open_fiscal_journal()

        return r

    def wkf_action_close(self, cr, uid, ids, context=None):
        r = super(pos_session, self).wkf_action_close(
            cr, uid, ids, context=context)
        # Cierre de caja, Informe Z o X
        for sess in [s for s in self.browse(cr, uid, ids)
                     if s.config_id.journal_id.use_fiscal_printer and
                     s.config_id.journal_id.fiscal_printer_id]:
            if sess.config_id.fpoc_close_report == 'z_report':
                sess.config_id.journal_id.close_fiscal_journal()
            elif sess.config_id.fpoc_close_report == 'x_report':
                sess.config_id.journal_id.shift_change()
            pass
        return r
pos_session()


class pos_order(osv.osv):
    _inherit = "pos.order"

    def _check_printer(self, journal):
        if not journal.use_fiscal_printer:
            return False

        if not journal.fiscal_printer_id:
            raise osv.except_osv(
                _('Error'),
                _('You must set a fiscal printer for the journal'))

        if journal.fiscal_printer_state not in ['ready']:
            raise osv.except_osv(
                _('Error!'),
                _('Printer is not ready to print.'))

        if journal.fiscal_printer_fiscal_state not in ['open']:
            raise osv.except_osv(
                _('Error!'),
                _('You can\'t print in a closed printer.'))

        if journal.fiscal_printer_paper_state not in ['ok']:
            raise osv.except_osv(
                _('Error!'),
                _('You can\'t print in low level of paper printer.'))

        if not journal.fiscal_printer_anon_partner_id:
            raise osv.except_osv(
                _('Error'),
                _('You must set anonymous partner to the journal.'))

        return True

    def create_from_ui(self, cr, uid, orders, context=None):
        session_obj = self.pool.get('pos.session')
        partner_obj = self.pool.get('res.partner')
        user_obj = self.pool.get('res.users')
        product_obj = self.pool.get('product.product')
        journal_obj = self.pool.get('account.journal')

        r = super(pos_order, self).create_from_ui(
            cr, uid, orders, context=context)
        for idx, _id in enumerate(r):
            data = orders[idx]['data']
            session = session_obj.browse(cr, uid, data['pos_session_id'])
            journal = session.config_id.journal_id
            user = user_obj.browse(cr, uid, data['user_id'])

            if not self._check_printer(journal):
                continue

            partner = partner_obj.browse(cr, uid, data['partner_id'])
            if not partner:
                partner = journal.fiscal_printer_anon_partner_id

            ticket = {
                "turist_ticket": False,
                "debit_note": False,
                "partner": {
                    "name": partner.name,
                    "name_2": "",
                    "address": partner.street,
                    "address_2": partner.city,
                    "address_3": partner.country_id.name,
                    "document_type": document_type_map.get(
                        partner.document_type_id.code, "D"),
                    "document_number": partner.document_number,
                    "responsability": responsability_map.get(
                        partner.responsability_id.code, "F"),
                },
                "related_document": _("No picking"),
                "related_document_2": "",
                "turist_check": "",
                "lines": [],
                "payments": [],
                "cut_paper": True,
                "electronic_answer": False,
                "print_return_attribute": False,
                "current_account_automatic_pay": False,
                "print_quantities": True,
                "tail_no": 1 if user.name else 0,
                "tail_text": _("Saleman: %s") % user.name if user.name else "",
                "tail_no_2": 0,
                "tail_text_2": "",
                "tail_no_3": 0,
                "tail_text_3": "",
            }
            for op1, op2, line in data['lines']:
                product = product_obj.browse(cr, uid, line['product_id'])
                ticket["lines"].append({
                    "item_action": "sale_item",
                    "as_gross": False,
                    "send_subtotal": True,
                    "check_item": False,
                    "collect_type": "q",
                    "large_label": "",
                    "first_line_label": "",
                    "description": "",
                    "description_2": "",
                    "description_3": "",
                    "description_4": "",
                    "item_description": product.name,
                    "quantity": line['qty'],
                    "unit_price": line['price_unit'],
                    "vat_rate": 0,
                    "fixed_taxes": 0,
                    "taxes_rate": 0
                })
                if line['discount'] > 0:
                    ticket["lines"].append({
                        "item_action": "discount_item",
                        "as_gross": False,
                        "send_subtotal": True,
                        "check_item": False,
                        "collect_type": "q",
                        "large_label": "",
                        "first_line_label": "",
                        "description": "",
                        "description_2": "",
                        "description_3": "",
                        "description_4": "",
                        "item_description": "%5.2f%%" % line['discount'],
                        "quantity": line['qty'],
                        "unit_price":
                        line['price_unit'] * (line['discount']/100.),
                        "vat_rate": 0.0,
                        "fixed_taxes": 0,
                        "taxes_rate": 0
                    })
            for op1, op2, pay in data['statement_ids']:
                payment_journal = journal_obj.browse(cr, uid, pay['journal_id'])
                ticket["payments"].append({
                    "type": "pay",
                    "extra_description": "",
                    "description": payment_journal.name,
                    "amount": pay['amount'],
                })

            journal.make_fiscal_ticket(ticket)

        return r
pos_order()

# v:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
