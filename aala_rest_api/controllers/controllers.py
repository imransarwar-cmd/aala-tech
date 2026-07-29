# -*- coding: utf-8 -*-
import json
import requests
from odoo import http
from odoo.http import request
import logging
_logger = logging.getLogger(__name__)
import base64

class AalaRestApiController(http.Controller):

    # Odoo 18+ repurposed type='json' to mean a plain JSON body/response
    # with no envelope. This handler was written for the OLD JSON-RPC
    # 2.0 envelope (params wrapped, result/error wrapped in the
    # response) -- that behavior now lives under type='jsonrpc'. Using
    # type='jsonrpc' here keeps this endpoint's request/response shape
    # unchanged for any existing client calling it.
    @http.route('/rest/login', type='jsonrpc', auth="public", csrf=False)
    def login_user(self, username, password, db):
        url_root = request.httprequest.url_root
        db = 'odoo'
        auth_url = url_root + "web/session/authenticate/"
        headers = {'Content-type': 'application/json'}
        data = {
            "jsonrpc": "2.0",
            "params": {
                "login": username,
                "password": password,
                "db": db
            }
        }
        res = requests.post(auth_url, data=json.dumps(data), headers=headers)
        try:
            session_id = res.cookies["session_id"]
            user = json.loads(res.text)
            user["result"]["session_id"] = session_id
            data = {
                "session": session_id,
                "uid": user["result"]["uid"],
            }
            res = {
                'status': True,
                'data': data
            }
        except Exception:
            return "Invalid credentials."
        return res

    @http.route('/rest/home', type='http', auth='user', csrf=False)
    def rest_home(self):
        try:
            banner_list = []
            product_list = []

            banners = request.env["banner.master"].sudo().search([])
            for banner in banners:
                image_url = '/web/image/banner.master/%s/image' % banner.id
                banner_list.append(image_url)

            systems = request.env["system.master"].sudo().search([])
            for system in systems:
                image = '/web/image/system.master/%s/image' % system.id
                banner_image = '/web/image/system.master/%s/banner_image' % system.id
                product_list.append({
                    'name': system.name,
                    'image': image,
                    'banner_image': banner_image,
                    'division': system.division.name,
                    'description': system.description,
                    'url': system.url
                })

            vals_list = {'banner_list': banner_list, 'product_list': product_list}
            data = {'status': 200, 'message': 'Success', 'response': vals_list}
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            res = {
                'status': 500,
                'message': str(e)
            }
            return request.make_response(
                json.dumps(res),
                headers=[('Content-Type', 'application/json')]
            )

    @http.route('/rest/brand/list', type='http', auth='user', csrf=False)
    def brand_list(self):
        try:
            brand_list = []
            brands = request.env["product.brand"].sudo().search([])
            for brand in brands:
                image = '/web/image/product.brand/%s/image' % brand.id
                banner_image = '/web/image/product.brand/%s/banner_image' % brand.id
                brand_list.append({
                    'name': brand.name,
                    'image': image,
                    'banner_image': banner_image,
                    'division': brand.division.name,
                    'description': brand.description,
                    'url': brand.url
                })
            data = {'status': 200, 'message': 'Success', 'response': brand_list}
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            res = {
                'status': 500,
                'message': str(e)
            }
            return request.make_response(
                json.dumps(res),
                headers=[('Content-Type', 'application/json')]
            )

    @http.route('/rest/product/list', type='http', auth='user', csrf=False)
    def product_list(self):
        try:
            product_list = []
            systems = request.env["system.master"].sudo().search([])
            for system in systems:
                image = '/web/image/system.master/%s/image' % system.id
                banner_image = '/web/image/system.master/%s/banner_image' % system.id
                product_list.append({
                    'name': system.name,
                    'image': image,
                    'banner_image': banner_image,
                    'division': system.division.name,
                    'description': system.description,
                    'url': system.url

                })
            data = {'status': 200, 'message': 'Success', 'response': product_list}
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            res = {
                'status': 500,
                'message': str(e)
            }
            return request.make_response(
                json.dumps(res),
                headers=[('Content-Type', 'application/json')]
            )

    @http.route('/rest/quotation/list', type='http', auth='user', csrf=False)
    def quotation_list(self):
        try:
            active_list = []
            complete_list = []
            uid = request.env.user.partner_id.id
            company_id = request.env.user.partner_id.parent_id.id

            sale_order = request.env["sale.order"].sudo().search([('partner_id', 'in', (uid, company_id))])
            sale_count = request.env["sale.order"].sudo().search_count([('partner_id', 'in', (uid, company_id)),
                                                                        ('state', 'in', ('sale', 'done'))])
            quotation_count = request.env["sale.order"].sudo().search_count(
                [('partner_id', 'in', (uid, company_id)), ('state', '=', 'draft')])
            for orders in sale_order:
                vals_list = {
                    'name': orders.project,
                    'product': orders.system.name,
                    'number': orders.name,
                    'price': orders.amount_total,
                    'date': orders.date_order.strftime('%b %d, %Y')
                }
                if orders.state in ('draft', 'sale'):
                    active_list.append(vals_list)
                elif orders.state == 'done':
                    complete_list.append(vals_list)
            vals = {'sale_count': sale_count, 'quotation_count': quotation_count, 'active': active_list,
                    'complete': complete_list}
            data = {'status': 200, 'message': 'Success', 'response': vals}
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            res = {
                'status': 500,
                'message': str(e)
            }
            return request.make_response(
                json.dumps(res),
                headers=[('Content-Type', 'application/json')]
            )

    @http.route('/rest/project/list', type='http', auth='user', csrf=False)
    def project_list(self):
        try:
            active_list = []
            complete_list = []
            status = []
            team_list =[]
            uid = request.env.user.partner_id.id
            company_id = request.env.user.partner_id.parent_id.id
            projects = request.env["project.project"].sudo().search([('partner_id', 'in', (uid, company_id))])
            print('projects',projects)
            for project in projects:
                for rec in project.project_status:
                    vals = {
                        'stage': rec.stage.name,
                        'status': rec.status.name,
                        'remarks': rec.remarks.name,
                        'date':  rec.date.strftime('%b %d, %Y') if rec.date else False}
                    status.append(vals)

                vals_list = {
                    'name': project.name,
                    'product': project.system.name,
                    'status': status,
                    'team': team_list
                }
                for team in project.team:
                    name = team.name
                    t_leader = team.team_leader.sudo()
                    leader = {'name': team.team_leader.name,
                              'title': team.team_leader.job_title,
                              # 'image': team.team_leader.name,
                              'image': '/public/employee/image/%s' % t_leader.id,
                              'phone': team.team_leader.mobile_phone,
                              'email': team.team_leader.work_email,
                     }
                    members = []
                    for rec in team.team:
                        rec.sudo()
                        teams = {'name': rec.name,
                                  'title': rec.job_title,
                                  # 'image': rec.name,
                                  'image': '/public/employee/image/%s' % rec.id,
                                  'phone': rec.mobile_phone,
                                  'email': rec.work_email,
                                  }
                        members.append(teams)
                    team_list.append({
                        'name' : team.name,
                        'leader': leader,
                        'members':members
                    })

                if project.stage_id.id == 2:
                    active_list.append(vals_list)
                elif project.stage_id.id == 3:
                    complete_list.append(vals_list)
            vals = {'active': active_list, 'complete': complete_list}
            data = {'status': 200, 'message': 'Success', 'response': vals}
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            res = {
                'status': 500,
                'message': str(e)
            }
            return request.make_response(
                json.dumps(res),
                headers=[('Content-Type', 'application/json')]
            )

    @http.route(['/public/employee/image/<int:employee_id>'], type='http', auth='public', website=True)
    def public_employee_image(self, employee_id, **kwargs):
        employee = request.env['hr.employee'].sudo().browse(employee_id)
        if not employee.exists() or not employee.image_128:
            return request.not_found()

        image_data = base64.b64decode(employee.image_128)
        return request.make_response(
            image_data,
            headers=[('Content-Type', 'image/png')]
        )
    @http.route('/rest/about/company', type='http', auth='user', csrf=False)
    def about_company(self):
        try:
            company = request.env["about.company"].sudo().search([],limit=1)
            vals = {
                'title':company['name'],
                'image': '/web/image/about.company/%s/image' % company.id,
                'url': company['url'],
                'description': company['description']
            }

            data = {'status': 200, 'message': 'Success', 'response': vals}
            return request.make_response(
                json.dumps(data),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            res = {
                'status': 500,
                'message': str(e)
            }
            return request.make_response(
                json.dumps(res),
                headers=[('Content-Type', 'application/json')]
            )
