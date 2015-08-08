# coding: utf-8
from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning, RedirectWarning
import time


class History(models.Model):
    _name = 'anytracker.history'
    _description = 'History of ticket'

    create_uid = fields.Many2one('res.users', 'User', readonly=True)
    create_date = fields.Datetime('Create Date', readonly=True)
    modification = fields.Text('Modification', readonly=True)


class Ticket(models.Model):
    _inherit = 'anytracker.ticket'

    history_ids = fields.Many2many(
        'anytracker.history',
        'anytracker_ticket_history_rel',
        'ticket_id',
        'history_id',
        'History')

    def _add_history(self, cr, uid, values, context=None):
        if not context:
            context = {}
        vals = ""
        if context.get('import_mindmap', False):
            vals += _("Update from Import MindMap\n")

        def _all2many(name, obj, val):
            if not val:
                return ""
            vals = _('Modify field %s\n') % name
            obj = self.pool.get(obj)
            for i in val:
                vals += " => "
                if i[0] == 0:
                    vals += _('Create new value %s') % i[2].get('name')
                elif i[0] == 1:
                    iname = i[2].get('name')
                    if not iname:
                        iname = obj.name_get(cr, uid, [i[1]], context=context)[0][1]
                    vals += _('Modify value %s') % iname
                elif i[0] == 2:
                    iname = obj.name_get(cr, uid, [i[1]], context=context)[0][1]
                    vals += _('Remove value %s') % iname
                elif i[0] == 3:
                    iname = obj.name_get(cr, uid, [i[1]], context=context)[0][1]
                    vals += _('Unlink value %s') % iname
                elif i[0] == 4:
                    iname = obj.name_get(cr, uid, [i[1]], context=context)[0][1]
                    vals += _('Link value %s') % iname
                elif i[0] == 5:
                    iname = obj.name_get(cr, uid, [i[1]], context=context)[0][1]
                    vals += _('Unlink all value %s') % iname
                elif i[0] == 6:
                    iname = obj.name_get(cr, uid, i[1], context=context)
                    vals += _('Unlink all value  and add:') % iname
                    for y, z in iname:
                        vals += '\n   * ' + z

                vals += '\n'

            return vals

        def _many2one(fieldname, obj, val):
            if not val:
                return ""
            obj = self.pool.get(obj)
            nameget = obj.name_get(cr, uid, [val], context=context)[0][1]
            return _('Modify field %s with new valeur %s\n') % (fieldname, nameget)

        for k, v in values.items():
            if k == 'stage_id':
                vals += _many2one(k, 'anytracker.stage', v)
            elif k == 'history_ids':
                continue
            elif k == 'parent_id':
                vals += _many2one(k, 'anytracker.ticket', v)
            elif k == 'requester_id':
                vals += _many2one(k, 'res.users', v)
            elif k == 'child_ids':
                vals += _all2many(k, 'anytracker.ticket', v)
            elif k == 'duration':
                col = dict(self._columns[k].selection)
                vals += _('Modify field %s with new valeur %s\n') % (k, col.get(v))
            else:
                vals += _('Modify field %s with new valeur %s\n') % (k, v)

        values['history_ids'] = [(0, 0, {'modification': vals})]
        return values

    def create(self, cr, uid, values, context=None):
        if values.get('id_mindmap'):
            # Create by import
            values['modified_openerp'] = values.get('modified_mindmap')
        else:
            # TODO generate id_mindmap
            # TODO generate time
            pass
        values = self._add_history(cr, uid, values, context=context)
        return super(Ticket, self).create(cr, uid, values, context=context)

    def write(self, cr, uid, ids, values, context=None):
        if not context:
            context = {}

        def _be_updated():
            for i in ('name', 'description', 'rating_ids', 'stage_id', 'parent_id'):
                if values.get(i):
                    return True
            return False

        if values.get('modified_mindmap'):
            for i in self.read(cr, uid, ids, ['name', 'modified_openerp'], context=context):
                if values['modified_mindmap'] < i['modified_openerp']:
                    raise except_orm(_('Error'),
                                     _('You can t update the ticket %s') % i['name'])
        elif context.get('import_mindmap', False):
            # description and complexity
            pass  # TODO
        elif _be_updated():
            values['modified_openerp'] = time.strftime('%Y-%m-%d %H:%M:%S')
        values = self._add_history(cr, uid, values, context=context)
        return super(Ticket, self).write(cr, uid, ids, values, context=context)
