from sibtmvar.apis import apiservices as api
from sibtmvar.microservices import configuration as conf, rankdoc as rd
from sibtmvar.microservices import cache
from sibtmvar.microservices import query as qu

def rankLit(request, conf_mode="prod", conf_file=None):
    ''' Retrieves a ranked set of documents, highlighted with a set of the query entites'''

    # Initialize the output variable
    output = None
    errors = []

    # Initialize the configuration
    if conf_file is None:
        conf_file = conf.Configuration(conf_mode)
        # Cache error handling
        errors += conf_file.errors

    # Log the query
    ip_address = api.processIpParameters(request)
    if not ('log' in request.args and request.args['log'] == "false"):
        api.logQuery(request, "ranklit", conf_file, ip_address)

    # Settings
    conf_file = api.processSettingsParameters(conf_file, request)

    # Remove the unique id from the query (enable to search for a cached version)
    unique_id = api.processIdParameters(request)
    url = str(request.url)
    url = url.replace("&uniqueId="+unique_id, "")

    # If the result is available in cache and the user accepts to use cache
    api_cache = cache.Cache("ranklit", url, "json", conf_file=conf_file)
    if api_cache.isInCache():

        # Reload the cache file
        output = api_cache.loadFromCache()

        # handle errors
        errors += api_cache.errors

    # If not in cache or cache failed
    if output is None:

        # Process all the parameters
        disease_txt, gen_vars_txt, gender_txt, age_txt = api.processCaseParameters(request)

        # Normalize the query
        query = qu.Query(conf_file)
        query.setDisease(disease_txt)
        query.setGenVars(gen_vars_txt)
        query.setGender(gender_txt)
        query.setAge(age_txt)

        # Initialize the json output
        output = {}
        output['unique_id'] = unique_id

        # Add settings to the output
        output['settings'] = api.returnSettingsAsJson(conf_file)

        # Add the query to the output
        output['query'] = query.getInitQuery()

        # Add the normalized query to the output
        output['normalized_query'] = query.getNormQuery()

        # Handle query errors
        errors += query.errors

        # Initialize the publication json part
        output['publications'] = {}

        # Fetch each document
        for collection in conf_file.settings['settings_user']['collections']:
            ranker = rd.RankDoc(query, collection, conf_file=conf_file)
            ranker.process()
            output['publications'][collection] = ranker.getJson()
            errors += ranker.errors

        # Report errors in the json (norm, fetch)
        output['errors'] = []
        for error in errors:
            if error not in output['errors']:
                output['errors'].append(error)

    # Update the unique id (useful when the cache file was generated by another user)
    if unique_id is not None:
        output['unique_id'] = unique_id

    # Display the output for the user
    return (api.buildOutput(output, conf_file, errors, api_cache))