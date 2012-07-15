# -*- coding: utf-8 -*-
from osv import osv, fields
from tools.translate import _
from xml import sax
from datetime import datetime
from cStringIO import StringIO
from base64 import b64decode
import time


class import_freemind_wizard(osv.osv_memory):
    _name = 'import.freemind.wizard'
    _description = 'Import freemind .mm file for generate anytracker tree'
    _columns = {
        'ticket_id': fields.many2one('anytracker.ticket', 'Ticket', domain="[('parent_id', '=', False)]"),
        'mindmap_content': fields.binary(_('File'), required=True),
        'green_complexity': fields.many2one('anytracker.complexity', 'green complexity', required=True),
        'orange_complexity': fields.many2one('anytracker.complexity', 'orange complexity', required=True),
        'red_complexity': fields.many2one('anytracker.complexity', 'red complexity', required=True),
    }

    def execute_import(self, cr, uid, ids, context=None):
        '''Launch import of nn file from freemind'''
        for wizard in self.browse(cr, uid, ids, context=context):
            complexity_dict = {'green_complexity_id': wizard.green_complexity.id or False,
                               'orange_complexity_id': wizard.orange_complexity.id or False,
                               'red_complexity_id': wizard.red_complexity.id or False,
                               }
            ticket_id = wizard.ticket_id and wizard.ticket_id.id or False
            content_handler = FreemindContentHandler(cr, uid, self.pool, ticket_id, complexity_dict)
            error_handler = FreemindErrorHandler()
            sax.parse(StringIO(b64decode(wizard.mindmap_content)),
                      content_handler, error_handler)
        return {'type': 'ir.actions.act_window_close'}

import_freemind_wizard()


class FreemindContentHandler(sax.ContentHandler):
    '''Handling event of sax xml parser'''

    def __init__(self, cr, uid, pool, ticket_id, complexity_dict):
        '''get element for access to openobject pool and db cursor'''
        self.cr = cr
        self.uid = uid
        self.pool = pool
        self.ticket_id = ticket_id
        self.parent_ids = []
        self.updated_ticket_ids = []
        self.complexity_dict = complexity_dict
        self.rich_content_buffer = False
        self.context = self.pool.get('res.users').context_get(cr, uid, uid)
        self.context['import_mindmap'] = True

    def startElement(self, name, attrs):
        names = attrs.getNames()
        any_tick_pool = self.pool.get('anytracker.ticket')
        stage_pool = self.pool.get('anytracker.stage')
        if name in ['node']:
            text_name = ''
            if 'TEXT' in names:
                text_name = attrs.getValue("TEXT")
            else:
                text_name = ''
            if len(self.parent_ids) == 0:
                self.parent_id = False
            else:
                self.parent_id = self.parent_ids[-1:][0]['osv_id']

            modified_mindmap = datetime.fromtimestamp(int(attrs.getValue('MODIFIED'))/1000.0)
            modified_mindmap = datetime.strftime(modified_mindmap, '%Y-%m-%d %H:%M:%S')
            created_mindmap = datetime.fromtimestamp(int(attrs.getValue('CREATED'))/1000.0)
            created_mindmap = datetime.strftime(created_mindmap, '%Y-%m-%d %H:%M:%S')
            id_mindmap = attrs.getValue('ID')
            vals = {
                'name': text_name,
                'parent_id': self.parent_id,
                'id_mindmap': id_mindmap,
                'modified_mindmap': modified_mindmap,
                'created_mindmap': created_mindmap,
                'modified_openerp': modified_mindmap,
            }
            domain = [
                ('id_mindmap', '=', id_mindmap),
                ('created_mindmap', '=', created_mindmap),
            ]
            if self.parent_id:
                domain.append(('parent_id', '=', self.parent_id))
            elif self.ticket_id:
                domain.append(('id', '=', self.ticket_id))
            osv_id = any_tick_pool.search(self.cr, self.uid, domain,
                    context=self.context)
            if (not osv_id) or (not self.parent_id and not self.ticket_id):
                osv_id = any_tick_pool.create(self.cr, self.uid, vals, context=self.context)
            else:
                any_tick_pool.write(self.cr, self.uid, osv_id, vals, context=self.context)
                osv_id = osv_id[0]
            self.parent_ids.append({'id': id_mindmap, 'osv_id': osv_id})
            self.updated_ticket_ids.append(osv_id)
        # rich content
        if name in ['richcontent']:
            self.rich_content_buffer = ''
        #if name in ['html', 'head', 'body', 'p']:
            #self.rich_content_buffer += '<' + name + '>'
        # icon
        if name in ['icon']:
            icon = attrs.getValue('BUILTIN')
            if icon == 'flag-green':
                complexity_id = self.complexity_dict['green_complexity_id']
            elif icon == 'flag-orange':
                complexity_id = self.complexity_dict['orange_complexity_id']
            elif icon == 'flag-red':
                complexity_id = self.complexity_dict['red_complexity_id']
            else:
                complexity_id = False
            if complexity_id:
                self.pool.get('anytracker.rating').create(
                    self.cr, self.uid,
                    {'ticket_id': self.parent_ids[-1:][0]['osv_id'],
                     'complexity_id': complexity_id,
                     'user_id': self.uid,
                     'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                    },
                    context=self.context)

    def characters(self, content):
        content = content.strip()
        if content != '':
            if self.rich_content_buffer != False:
                self.rich_content_buffer += content

    def endElement(self, name):
        any_tick_pool = self.pool.get('anytracker.ticket')
        if name in ['node']:
            if len(self.parent_ids) != 0:
                self.parent_ids.pop()
        # rich content
        #if name in ['html', 'head', 'body', 'p']:
        #    self.rich_content_buffer += '</' + name + '>'
        if name in ['richcontent']:
            any_tick_pool.write(self.cr, self.uid, self.parent_ids[-1:][0]['osv_id'],
                {'description': self.rich_content_buffer}, context=self.context)
            self.rich_content_buffer = False

    def endDocument(self):
        ticket_obj = self.pool.get('anytracker.ticket')
        first_ticket_id = self.updated_ticket_ids[0]
        if self.ticket_id:
            if self.ticket_id != first_ticket_id:
                raise osv.except_osv(_('Error'), _('You try to update the wrong main ticket'))
        domain = [
            ('id', 'child_of', first_ticket_id),  # children of main ticket
            ('id', 'not in', self.updated_ticket_ids),  # ticket not updated
        ]
        deleted_ticket_ids = ticket_obj.search(self.cr, self.uid, domain, context=self.context)
        ticket_obj.unlink(self.cr, self.uid, deleted_ticket_ids, context=self.context)

class FreemindErrorHandler(sax.ErrorHandler):
    '''Handling error event of sax xml parser'''

    def error(self, exception):
        "Handle a recoverable error."
        raise osv.except_osv(_('Error !'),
                        exception.args[0])

    def fatalError(self, exception):
        "Handle a non-recoverable error."
        raise osv.except_osv(_('Error !'),
                        exception.args[0])

    def warning(self, exception):
        "Handle a warning."
        raise osv.except_osv(_('Warning !'),
                        exception.args[0])

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4: