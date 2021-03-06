from flask import Flask, request, jsonify
from flask_restx import Api, Resource, fields
from agent.fabric import Fabric
from agent.sflow import sFlow
from agent.syslog import Syslog
from agent.netconf import Netconf
from agent.openconfig import OpenConfig
from common.exceptions import InvalidUsage
from agent.snmp import SNMP

app = Flask(__name__)
api = Api(app, version='1.0', title='Simulator Agent API',
          description='Simulator Agent API')

@app.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    response = jsonify(error.to_dict())
    response.status_code = error.status_code
    return response

# Register Fabric wide operations api
ns_fabric = api.namespace('fabric', description='Fabric wide Apis')
fabric_put_schema = {
    'address_pool': fields.String(required=True,
        description='List of address pools - eg: [("10.1.1.10", "10.1.1.20"),'
                    ' ("10.1.1.30", "10.1.1.40")]'),
    'n_leafs': fields.Integer(required=True,
        description='No of leafs in the fabric'),
    'n_spines': fields.Integer(required=True,
        description='No of spines in the fabric'),
    'n_border_leafs': fields.Integer(
        description='No of border leafs in the fabric'),
    'n_super_spines': fields.Integer(
        description='No of super spines in the fabric'),
    'n_pifs': fields.Integer(
        description='No of physical interfaces in each Leaf - eg: 48'),
    'collector': fields.String(
        description='Address of the sflow collector if action is start')
}
fabric_post_schema = dict(fabric_put_schema)
fabric_post_schema.update({
    'interface': fields.String(required=True,
        description='Physical interface on the host - eg: enp129s0f1'),
    'subnet': fields.String(required=True,
        description='CIDR to assign to simulator instances - eg: 10.1.1.0/24'),
    'gateway': fields.String(required=True,
        description='Gateway address for the simulator instances - eg: 10.1.1.254')})
fabric_put_model = api.model('fabric_put_model', fabric_put_schema)
fabric_post_model = api.model('fabric_post_model', fabric_post_schema)

@ns_fabric.route("/<string:fabric_name>")
class FlaskFabric(Resource):
    def get(self, fabric_name):
        return Fabric.get(fabric_name)

    @ns_fabric.expect(fabric_post_model)
    def post(self, fabric_name):
        data = request.get_json(force=True)
        return Fabric().post(fabric_name, **data)

    @ns_fabric.expect(fabric_put_model)
    def put(self, fabric_name):
        data = request.get_json(force=True)
        return Fabric().put(fabric_name, **data)

    def delete(self, fabric_name):
        return Fabric.delete(fabric_name)

@ns_fabric.route("/")
class FlaskFabricList(Resource):
    def get(self):
        return Fabric.get()

# Register sFlow engine apis
ns_sflow = api.namespace('sflow', description='sFlow start/stop actions')
sflow_schema = {
    'action': fields.String(required=True,
        description='start or stop sflows'),
    'direction': fields.String(required=True,
        description='ingress or egress direction for sflow collection'),
    'bms_per_router': fields.String(required=True,
        description='No of BMS servers per Device (floor and not ceil)'),
    'n_flows': fields.Integer(required=True,
        description='No of sampled flows if action is "start"')
}
sflow_model = api.model('sflow_model', sflow_schema)
@ns_sflow.route("/<string:fabric_name>")
class FlaskSFlow(Resource):
    @ns_sflow.expect(sflow_model)
    def post(self, fabric_name):
        data = request.get_json(force=True)
        sFlow().post(fabric_name, **data)

# Register device specific apis
ns_device = api.namespace('device', description='Update a physical router simulator')
device_schema = {
    'manager': fields.String(required=True,
        description='JFM Manager address'),
    'secret': fields.String(required=True,
        description='Secret key authenticating with manager'),
    'device_id': fields.String(required=True,
        description='Device id of the device in the manager')
}
device_model = api.model('device_model', device_schema)
@ns_device.route("/<string:device_name>")
class FlaskDevice(Resource):
    @ns_device.expect(device_model)
    def put(self, device_name):
        data = request.get_json(force=True)
        Fabric().update_device(device_name, **data)

# Register netconf engine apis
ns_netconf = api.namespace('netconf', description='Send events to netconf engine')
netconf_schema = {
    'kv_pairs': fields.List(fields.Nested(api.model('kv_model',
        {'key': fields.String, 'value': fields.String}))),
    'template': fields.Nested(api.model('template_model',
        {'rpc_name': fields.String, 'content': fields.String})),
    'devices': fields.List(fields.String, description='List of devices')
}
netconf_model = api.model('netconf_model', netconf_schema)
@ns_netconf.route("/<string:fabric_name>")
class FlaskNetconf(Resource):
    def get(self, fabric_name):
        devices = request.args.get('devices')
        raw = request.args.get('raw')
        if devices:
            devices = devices.split(',')
        return Netconf().get(fabric_name, devices, raw)

    @ns_netconf.expect(netconf_model)
    def post(self, fabric_name):
        data = request.get_json(force=True)
        Netconf().post(fabric_name, **data)


ns_snmp = api.namespace('snmp', description='Send events to snmp engine')
snmp_schema = {
    'oids': fields.List(fields.Nested(api.model('oid_model',
        {'oid': fields.String, 'value': fields.String,
         'type': fields.String(enum=["Integer", "String", "OID", "Timeticks",
                                     "IPAddress", "Counter32", "Counter64",
                                     "Gauge32", "Opaque"])})), required=True),
    'devices': fields.List(fields.String, description='List of devices'),
    'trap': fields.String(description='Trap OID to send')
}
snmp_model = api.model('snmp_model', snmp_schema)
@ns_snmp.route("/<string:fabric_name>")
class FlaskSNMP(Resource):
    @ns_snmp.expect(snmp_model)
    def post(self, fabric_name):
        data = request.get_json(force=True)
        SNMP().post(fabric_name, **data)

ns_syslog = api.namespace('syslog', description='Send syslog messages to server')
syslog_schema = {
    'devices': fields.List(fields.String, description='List of devices'),
    'level': fields.String(description='Log level', required=True),
    'facility': fields.String(description='facility type', required=True),
    'message': fields.String(description='Syslog message', required=True)
}
syslog_model = api.model('syslog_model', syslog_schema)
@ns_syslog.route("/<string:fabric_name>")
class FlaskSyslog(Resource):
    @ns_syslog.expect(syslog_model)
    def post(self, fabric_name):
        data = request.get_json(force=True)
        Syslog().post(fabric_name, **data)

ns_openconfig = api.namespace('openconfig', description='Send events to openconfig engine')
@ns_openconfig.route("/<string:fabric_name>")
class FlaskOpenconfig(Resource):
    def post(self, fabric_name):
        data = request.get_json(force=True)
        OpenConfig().post(fabric_name, data)


ns_snmp = api.namespace('snmp', description='Send events to snmp engine')
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=8989)
