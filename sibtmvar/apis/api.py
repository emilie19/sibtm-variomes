import flask
from flask import Response, request
from flask_cors import CORS, cross_origin

from sibtmvar.apis import apifetch as af
from sibtmvar.apis import apiranklit as arl
from sibtmvar.apis import apirankvar as arv
from sibtmvar.apis import apistatus as ast
from sibtmvar.microservices import configuration as conf
import requests

app = flask.Flask(__name__)
app.config["DEBUG"] = True
cors = CORS(app, resources={r"/api/*": {"origins": "*"}})
app.config['CORS_HEADERS'] = 'Content-Type'

# Select the prod or dev configuration files
conf_mode = "dev2023"

# Load the configuration file
conf_file = conf.Configuration(conf_mode)

#APIs for variomes services

@app.route('/api/isUp', methods=['GET'])
@cross_origin()
def isUp():
    ''' Fetch one or several documents and return them with highlights and statistics '''
    return Response("ok", content_type="text/plain; charset=utf-8")

@app.route('/api/fetchDoc', methods=['GET'])
@cross_origin()
def fetchDoc():
    ''' Fetch one or several documents and return them with highlights and statistics '''
    output = af.fetchDoc(request, conf_mode=conf_mode)
    return Response(output, content_type="application/json; charset=utf-8")

@app.route('/api/rankLit', methods=['GET'])
@cross_origin()
def rankLit():
    ''' Search and rank documents for one query '''
    output = arl.rankLit(request, conf_mode=conf_mode)
    return Response(output, content_type="application/json; charset=utf-8")

@app.route('/api/rankVar', methods=['GET', 'POST'])
@cross_origin()
def rankVar():
    ''' Search and rank variants for one file or query '''
    output = arv.rankVar(request, conf_mode=conf_mode)
    return Response(output, content_type="application/json; charset=utf-8")

@app.route('/api/getStatus', methods=['GET', 'POST'])
@cross_origin()
def getStatus():
    ''' Search and rank variants for one file or query '''
    output = ast.getStatus(request, conf_mode=conf_mode)
    return Response(output, content_type="application/json; charset=utf-8")

@app.route('/api/testsolr', methods=['GET', 'POST'])
@cross_origin()
def testSolr():
    ''' Search and rank variants for one file or query '''
    contents = requests.get("http://localhost:8995/solr/terminologies/select?q=*%3A*")
    return Response(contents, content_type="application/json; charset=utf-8")
	
# Run the API
app.run(host=conf_file.settings['api']['host'],port=conf_file.settings['api']['port'])
