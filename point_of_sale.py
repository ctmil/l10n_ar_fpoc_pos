# -*- coding: utf-8 -*-

import logging
import time

from openerp import tools
from openerp.osv import fields, osv
from openerp.tools.translate import _

from openerp.addons.l10n_ar_fpoc.invoice import document_type_map, responsability_map

responsability_map = {
    "1": "I", # Inscripto, 
    "2": "N", # No responsable, 
    "6": "M", # Monotributista,
    "4": "E", # Exento,
    "7": "U", # No categorizado,
    "5": "F", # Consumidor final,
    "13": "T", # Monotributista social,
}


class pos_session(osv.osv):
    _inherit = 'pos.session'

    def wkf_action_open(self, cr, uid, ids, context=None):
        r = super(pos_session, self).wkf_action_open(cr, uid, ids, context=context)
        # Apertura de caja.
        for sess in [ s for s in self.browse(cr, uid, ids)
                     if s.config_id.journal_id.use_fiscal_printer and
                        s.config_id.journal_id.fiscal_printer_id ]:
            fp_r = sess.config_id.journal_id.open_fiscal_journal()
            pass
        return r

    def wkf_action_close(self, cr, uid, ids, context=None):
        r = super(pos_session, self).wkf_action_close(cr, uid, ids, context=context)
        # Cierre de caja, Informe Z
        for sess in [ s for s in self.browse(cr, uid, ids)
                     if s.config_id.journal_id.use_fiscal_printer and
                        s.config_id.journal_id.fiscal_printer_id ]:
            fp_r = sess.config_id.journal_id.close_fiscal_journal()
            pass
        return r
pos_session()

class pos_order(osv.osv):
    _inherit = "pos.order"

    _columns = {
            'pos_order_id': fields.char('POS Order ID', readonly=True)
	}

    def create_from_ui_v3(self, cr, uid, orders, context=None):
        session_obj = self.pool.get('pos.session')
        partner_obj = self.pool.get('res.partner')
        user_obj = self.pool.get('res.users')
        product_obj = self.pool.get('product.product')
        journal_obj = self.pool.get('account.journal')

	order_id = None
        #r = super(pos_order, self).create_from_ui(cr, uid, orders, context=context)
        #for idx, _id in enumerate(r):
	for idx in orders:
            data = idx['data']
	    #order = self.pool.get('pos.order').browse(cr,uid,idx)	
            session = session_obj.browse(cr, uid, data['pos_session_id'])
            #session = session_id
            journal = session.config_id.journal_id
            #user = order.user_id
	    user = self.pool.get('res.users').browse(cr,uid,uid)

	    return_id = self.pool.get('pos.order').search(cr,uid,[('pos_order_id','=',data['uid'])])
	    if return_id:
		continue
            order_id = self._process_order(cr, uid, data, context=context)
	    return_id = self.pool.get('pos.order').write(cr,uid,order_id,{'pos_order_id': data['uid']})
	    order = self.pool.get('pos.order').browse(cr,uid,order_id)
	    if order_id:
		 order.signal_workflow('paid')

            if not journal.use_fiscal_printer:
                continue

            if not journal.fiscal_printer_id:
                raise osv.except_osv(_('Error'), _('You must set a fiscal printer for the journal'))

            if not journal.fiscal_printer_state in ['ready']:
                raise osv.except_osv(_('Error!'), _('Printer is not ready to print.'))

            if not journal.fiscal_printer_fiscal_state in ['open']:
                raise osv.except_osv(_('Error!'), _('You can\'t print in a closed printer.'))

            #if not journal.fiscal_printer_paper_state in ['ok']:
            #    raise osv.except_osv(_('Error!'), _('You can\'t print in low level of paper printer.'))

            if not journal.fiscal_printer_anon_partner_id:
                raise osv.except_osv(_('Error'), _('You must set anonymous partner to the journal.'))

            #partner = order.partner_id
	    partner = self.pool.get('res.partner').browse(cr,uid,data['partner_id'])
            #if not partner:
            #    partner = journal.fiscal_printer_anon_partner_id

	    #import pdb;pdb.set_trace()
            ticket={
                "turist_ticket": False,
                "debit_note": False,
                "partner": {
                    "name": partner.name,
                    "name_2": "",
                    "address": partner.street,
                    "address_2": partner.city,
                    "address_3": partner.country_id.name,
                    "document_type": document_type_map.get(partner.document_type_id.code, "D"),
                    "document_number": partner.document_number,
                    "responsability": responsability_map.get(partner.responsability_id.code, "F"),
                    #"responsability": partner.responsability_id.code or "F",
                },
                #"related_document": order.picking_id.name or _("No picking"),
                "related_document": _("No picking"),
                "related_document_2": "",
                "turist_check": "",
                "lines": [ ],
                "payments": [ ],
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
            #for line in order_lines:
                product = self.pool.get('product.product').browse(cr,uid,line['product_id'])
		tax_rate = 0
		for tax in product.taxes_id:
			tax_rate = tax.amount * 100
		description = ''
		if line.has_key('previous_discount') and line['previous_discount'] > 0:
			description = 'Dto - %'  + str(line['previous_discount'])
                ticket["lines"].append({
                    "item_action": "sale_item",
                    "as_gross": False,
                    "send_subtotal": True,
                    "check_item": False,
                    "collect_type": "q",
                    "large_label": "",
                    "first_line_label": "",
                    "description": description,
                    "description_2": "",
                    "description_3": "",
                    "description_4": "",
                    "item_description": product.name,
                    #"quantity": line['qty'],
                    #"unit_price": line['price_unit'],
                    "quantity": line['qty'],
                    "unit_price": line['price_unit'],
                    "vat_rate": tax_rate, # TODO
                    "fixed_taxes": 0,
                    "taxes_rate": 0
                })
                #if line['previous_discount'] > 0: 
			#ticket["lines"].append({
	                #    "item_action": "discount_item",
        	        #    "as_gross": False,
	                #    "send_subtotal": True,
        	        #    "check_item": False,
                	#    "collect_type": "q",
	                #    "large_label": "",
        	        #    "first_line_label": "",
                	#    "description": "",
	                #    "description_2": "",
        	        #    "description_3": "",
                	#    "description_4": "",
	                #    "item_description": "%5.2f%%" % line['previous_discount'],
        	        #    "quantity": 1,
                	#    "unit_price": line['price_unit'] * (line['previous_discount']/100),
	                #    "vat_rate": tax_rate, # TODO
        	        #    "fixed_taxes": 0,
                	#    "taxes_rate": 0
	                #})
            #for pay in order.statement_ids:
            for op1, op2, pay in data['statement_ids']:
                payment_journal = journal_obj.browse(cr, uid, pay['journal_id'])
                ticket["payments"].append({
                    "type": "pay",
                    "extra_description": "",
                    "description": payment_journal.name,
                    "amount": pay['amount'],
                })
            ticket_resp = journal.make_fiscal_ticket(ticket)
	    error_printing = False
	    if type(ticket_resp) == dict:
		if type(ticket_resp.values()) == list:
		    if 'error' in ticket_resp.values()[0]:
			error_printing = True	
	    if ticket_resp and not error_printing:
		if responsability_map.get(partner.responsability_id.code, "F") == 'F':
			ticket_number = journal.last_b_sale_document_completed
		else:
			ticket_number = journal.last_a_sale_document_completed

		vals_order = {
			'pos_reference': journal.point_of_sale + '-' + str(ticket_number).zfill(8)
			}
		return_id = self.pool.get('pos.order').write(cr,uid,order_id,vals_order)
        #return r
	if order_id:
		return [order_id]
	else:
	        return [-1] 


    def create_refund_from_ui_v3(self, cr, uid, orders, context=None):
        session_obj = self.pool.get('pos.session')
        partner_obj = self.pool.get('res.partner')
        user_obj = self.pool.get('res.users')
        product_obj = self.pool.get('product.product')
        journal_obj = self.pool.get('account.journal')

	#import pdb;pdb.set_trace()
        #r = super(pos_order, self).create_from_ui(cr, uid, orders, context=context)
        #for idx, _id in enumerate(r):
        for idx in orders:
            #data = orders[idx]['data']
            order = self.pool.get('pos.order').browse(cr,uid,idx)
            #session = session_obj.browse(cr, uid, data['pos_session_id'])
            session = order.session_id
            journal = session.config_id.journal_id
            user = order.user_id

            if not journal.use_fiscal_printer:
                continue

            if not journal.fiscal_printer_id:
                raise osv.except_osv(_('Error'), _('You must set a fiscal printer for the journal'))

            if not journal.fiscal_printer_state in ['ready']:
                raise osv.except_osv(_('Error!'), _('Printer is not ready to print.'))

            if not journal.fiscal_printer_fiscal_state in ['open']:
                raise osv.except_osv(_('Error!'), _('You can\'t print in a closed printer.'))

            #if not journal.fiscal_printer_paper_state in ['ok']:
            #    raise osv.except_osv(_('Error!'), _('You can\'t print in low level of paper printer.'))

            if not journal.fiscal_printer_anon_partner_id:
                raise osv.except_osv(_('Error'), _('You must set anonymous partner to the journal.'))

            partner = order.partner_id
            if not partner:
                partner = journal.fiscal_printer_anon_partner_id

            ticket={
                "turist_ticket": False,
                "debit_note": False,
                "partner": {
                    "name": partner.name,
                    "name_2": "",
                    "address": partner.street,
                    "address_2": partner.city,
                    "address_3": partner.country_id.name,
                    "document_type": document_type_map.get(partner.document_type_id.code, "D"),
                    "document_number": partner.document_number,
                    "responsability": responsability_map.get(partner.responsability_id.code, "F"),
                },
                "related_document": order.name or _("No related doc"),
                "related_document_2": "",
                "turist_check": "",
                "lines": [ ],
                "payments": [ ],
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
		"origin_document": order.origin_id.pos_reference or 'N/A'
            }
            #for op1, op2, line in data['lines']:
            for line in order.lines:
                product = line.product_id
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
                    #"quantity": line['qty'],
                    #"unit_price": line['price_unit'],
                    "quantity": line.qty * (-1),
                    "unit_price": line.price_unit,
                    "vat_rate": line.product_id.tax_rate * 100, # TODO
                    "fixed_taxes": 0,
                    "taxes_rate": 0
                })
            for pay in order.statement_ids:
                payment_journal = journal_obj.browse(cr, uid, pay.journal_id.id)
                ticket["payments"].append({
                    "type": "pay",
                    "extra_description": "",
                    "description": payment_journal.name,
                    "amount": pay.amount * (-1),
                })

            ticket_resp = journal.make_fiscal_refund_ticket(ticket)

            if ticket_resp:
                if responsability_map.get(partner.responsability_id.code, "F") == 'F':
                        ticket_number = journal.last_b_refund_document_completed
                else:
                        ticket_number = journal.last_a_refund_document_completed

                vals_order = {
                        'pos_reference': journal.point_of_sale + '-' + str(ticket_number).zfill(8)
                        }
                return_id = self.pool.get('pos.order').write(cr,uid,order.id,vals_order)

        #return r
        return None



pos_order()

# v:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
