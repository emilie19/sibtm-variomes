import re

from sibtmvar.microservices import highlight as hl
from sibtmvar.microservices import stats as st
from sibtmvar.microservices import configuration as conf
from sibtmvar.microservices import mapping as map
from sibtmvar.microservices import mongo as mg

class DocumentParser:
    '''
    The DocumentParser object stores a document (medline, pmc or ct) and generates a json with details

    Parameters
    ----------
    doc_id: str
        a document identifier
    collection: str
        the collection of the document
    conf_mode: str
        indicate which configuration file should be used (default: prod)
    conf_file: Configuration
        indicate a Configuration object to use (default: None)

    Attributes
    ----------
    conf_file: Configuration
        indicate a Configuration object to use (default: None)
    errors: list
        stores a list of errors with a json format
    doc_id: str
        a document identifier
    collection: str
        the collection of the document
    final_score: double
        the score of the document (default: 0)
    rank: int
        the rank of the document
    elastic_score: dict
        a set of scores
    fields_mapping: FieldsMapping
        the FieldsMapping object to convert field names
    ret_fields: dict
        a list of fields to return
    hl_fields: dict
        a list of fields to highlight
    hl_entities: dict
        a set of entities to tag: [{'type': '', 'id': '', 'main_term': '', query_term': '', all_terms: [''], 'match': 'exact|partial'}]
    stats: dict
        a set of statistics
    requested_fields: dict
        a set of fields + highlighted fields
    snippets: dict
        a set of sentences containing the variant from the query
    cleaned_snippets: dict
        a set of sentences containing the variant from the query with highlight
    '''

    def __init__(self, doc_id, collection, conf_file=None, conf_mode="prod"):
        ''' Initialize the document object'''

        # Initialize a variable to store errors
        self.errors = []

        # Load configuration file
        self.conf_file = conf_file
        if conf_file is None:
            self.conf_file = conf.Configuration(conf_mode)
            # Cache error handling
            self.errors += self.conf_file.errors

        # Store user request
        self.doc_id = doc_id
        self.collection = collection

        # Initialize variables
        self.elastic_scores = {}
        self.final_score = 0
        self.rank = 0
        self.requested_fields = {}
        self.snippets ={}

        # Initiate entities to highlight
        self.hl_entities = []

        # Load mapping
        self.fields_mapping = map.FieldsMapping(self.collection)

        # Mapping error handling
        self.errors += self.fields_mapping.errors

        # Check that the collection is valid
        if self.collection in self.conf_file.settings['settings_system']['collections']:

            # Load fields to return and to highlight
            self.ret_fields = self.fields_mapping.convertListFromUserNames(self.conf_file.settings['settings_user']['fetch_fields_' + self.collection])
            # Add pmid to requested fields in order to update the document ids
            if self.collection != "medline" and "pmid" not in self.ret_fields:
                self.ret_fields.append("pmid")
            self.hl_fields = self.fields_mapping.convertListToUserNames(self.conf_file.settings['settings_user']['hl_fields_' + self.collection])


    def setHighlightedEntities(self, hl_entities):
        ''' Define list of entities to highlight'''
        self.hl_entities = hl_entities

    def addScore(self, query_type, this_score, max_score):
        ''' Add a subscore for the document'''
        self.elastic_scores[query_type] = this_score / max_score

    def setFinalScore(self, final_score):
        ''' Set the final score of the document '''
        self.final_score = final_score

    def setRank(self, rank):
        ''' Set the rank of the document '''
        self.rank = rank

    def addSnippets(self, snippets_json):
        ''' Add a set of sentences containing the variants '''

        # For each section
        for section in snippets_json:
            if section not in self.snippets:
                self.snippets[section] = []
            # For each sentence of the section
            for sentence in snippets_json[section]:
                # Remove ES tagging
                sentence = sentence.replace("<em>", "")
                sentence = sentence.replace("</em>", "")
                # Store the sentence
                self.snippets[section].append(sentence)


    def addSnippetsCT(self, snippets_json):
        ''' Add a set of sentences containing the variants '''

        # For each section
        for element in snippets_json:
            section = element['section']
            sentence = element['text']
            if type(sentence) == list:
                sentence = (', ').join(sentence)
            if section not in self.snippets:
                self.snippets[section] = []
            self.snippets[section].append(sentence)


    def fetchMongo(self):
        ''' Retrieve document's information in MongoDB '''

        # Set source
        self.requested_fields['source'] = self.conf_file.settings['settings_system']['client_mongodb_' + self.collection] + "/" + self.conf_file.settings['settings_system']['mongodb_collection_' + self.collection]

        # Check that the collection is valid
        if self.collection in self.conf_file.settings['settings_system']['collections']:

            # Connect to Mongodb
            if self.collection == "ct":
                mongo = mg.Mongo(self.conf_file.settings['url']['mongodb_ct'])
                mongo.connectDb(self.conf_file.settings['settings_system']['client_mongodb_' + self.collection])

            else:
                mongo = mg.Mongo(self.conf_file.settings['url']['mongodb'])
                mongo.connectDb(self.conf_file.settings['settings_system']['client_mongodb_' + self.collection])

            # Query biomed to get document
            mongo_collection = self.conf_file.settings['settings_system']['mongodb_collection_' + self.collection]
            doc_json = mongo.query(mongo_collection, {"_id": self.doc_id})

            # If document is not retrieved, return a warning error
            if doc_json is None:
                self.errors.append({"level": "warning", "service": "mongodb", "description": "Document not found",
                                    "details": self.doc_id})

            # Update authors for pmc
            if doc_json is not None:
                document = doc_json
                if self.collection != "ct":
                    document = doc_json['document']
                authors_update = []
                if self.collection == "pmc":
                    for author in document['authors']:
                        author_name = author['name']
                        authors_update.append(author_name)
                    document['authors'] = authors_update

            # Close MongoDb
            mongo.closeClient()

            # Mongodb error handling
            self.errors += mongo.errors

            # If a document was retrieved
            if doc_json is not None:

                # Store requested json fields
                self.ret_fields.sort()
                for field in self.ret_fields:
                    if field in doc_json:
                        self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = doc_json[field]

    def fetchEs(self, doc_json):
        ''' Retrieve document's information in ES '''

        # Set source
        self.requested_fields['source'] = self.conf_file.settings['settings_system']['es_index_' + self.collection]

        # Set ARK if ARK
        if 'ARK' in doc_json['_source']:
            self.ark = doc_json['_source']['ARK']
        # Store requested fields
        self.ret_fields.sort()
        for field in self.ret_fields:
            if field in doc_json['_source']:
                if field == "comments_in" or field == "comments_on":
                    if doc_json['_source'][field] != "":
                        self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = doc_json['_source'][field].split("|")
                    else:
                        self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = []
                elif field == "authors" or field == "publication_types" or field == "article_type" or field == "mesh_terms" or field == "keywords" or field == "chemicals":
                    if doc_json['_source'][field] != "":
                        self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = doc_json['_source'][field].split("|")
                    else:
                        self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = []
                elif field == "language":
                    if self.collection == "pmc":
                        language = doc_json['_source'][field].lower()
                        if language == "":
                            language = "unknown"
                        self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = language
                else:
                    self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = doc_json['_source'][field]
            else:
                if field == "language" and self.collection == "medline":
                    language = "en"
                    if re.match(r"^\[.*\].$", doc_json['_source']["title"]):
                        language = "other"
                    self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = language
                if field == "language" and self.collection == "pmc":
                    self.requested_fields[self.fields_mapping.convertFieldToUserNames(field)] = "unknown"

    def processDocument(self):
        ''' Highlight, generates statistics, handle snippets, etc'''


        # Load statistics
        doc_id = self.doc_id
        if (self.collection == "pmc"):
            doc_id = self.requested_fields['pmcid']

        self.stats = st.DocStats(doc_id, self.collection, conf_file=self.conf_file)

        # Add population and ct in highlighted entities
        if 'information_extraction' in self.stats.details:
            ie_entities = []
            for ie_type in ['clinical_trials', 'populations']:
                for ie in self.stats.details['information_extraction'][ie_type]:
                    element = {"type": ie_type,
                               "id": ie['term'],
                               "query_term": ie['term'],
                               "main_term": ie['term'],
                               "all_terms": [],
                               "terminology": "none",
                               "match": "exact"}
                    ie_entities.append(element)

        # Highlight of requested fields
        for hl_field in self.hl_fields:
            if hl_field in self.requested_fields:

                text_to_highlight = self.requested_fields[hl_field]
                if type(self.requested_fields[hl_field]) == list:
                    text_to_highlight = '; '.join(self.requested_fields[hl_field])
                    self.requested_fields[hl_field] = text_to_highlight
                all_entities = self.hl_entities + ie_entities
                highlighter = hl.Highlight(text_to_highlight, all_entities)
                self.requested_fields[self.fields_mapping.convertFieldToUserNames(hl_field) + "_highlight"] = highlighter.highlighted_text

        # Load comments
        if ('comments_in' in self.ret_fields or 'comments_on' in self.ret_fields) and self.collection == "medline":
            self.loadComments()

        # Add date for ct
        if 'start_date' in self.ret_fields and self.collection == "ct":
            date_match = re.search('([1-3][0-9]{3})', self.requested_fields['start_date'] , re.IGNORECASE)
            if date_match:
                date = date_match.group(1)
                self.requested_fields['date'] = int(date)
            else:
                self.requested_fields['date'] = self.requested_fields['start_date']

        # Stats error handling
        self.errors += self.stats.errors

        # Convert file name
        convertEvidence = {'xls': 'table', 'csv': 'table', 'jpg': 'image', 'png': 'image'}

        # Process snipets
        self.cleaned_snippets = []
        for section, snippets in self.snippets.items():
            matchObj = re.match(r'((.*)\.(.*?)[xX]?)///ARK///(.*?)$', section)
            file = None
            if matchObj:
                section = matchObj.group(3)
                if section.lower() in convertEvidence:
                    section = convertEvidence[section.lower()]
                file = matchObj.group(1)
                ark = matchObj.group(4)
            sentences = list(dict.fromkeys(snippets))
            for sentence in sentences:
                json_snipet = {}
                json_snipet['section'] = section.lower()
                highlighter = hl.Highlight(sentence, self.hl_entities+ie_entities)
                json_snipet['text'] = highlighter.highlighted_text
                if file is not None:
                    json_snipet['file'] = file
                    json_snipet['ARK'] = ark
                    json_snipet['url'] = "https://www.ncbi.nlm.nih.gov/pmc/articles/"+self.pmcid+"/bin/"+file
                self.cleaned_snippets.append(json_snipet)

         # Update statistics
        self.stats.finalizeStats(self.hl_entities, self.requested_fields, self.cleaned_snippets)

    def loadComments(self):
        ''' Search for info for comments'''

        # If there is a comment
        if 'comments_in' in self.requested_fields or 'comments_on' in self.requested_fields :

            # Connect to Mongodb
            mongo = mg.Mongo(self.conf_file.settings['url']['mongodb'])
            mongo.connectDb(self.conf_file.settings['settings_system']['client_mongodb_' + self.collection])

            # Query biomed to get document
            mongo_collection = self.conf_file.settings['settings_system']['mongodb_collection_' + self.collection]

            # Get comments
            for comment_type in ['in', 'on']:
                updated_comments = []
                comments = self.requested_fields['comments_' + comment_type]
                for comment_id in comments:
                    comment_json = mongo.query(mongo_collection, {"_id": comment_id})
                    if comment_json is not None:
                        this_comment = {}
                        this_comment['id'] = comment_id
                        this_comment['collection'] = 'medline'
                        this_comment['date'] = int(comment_json['pubyear'])
                        this_comment['title'] = comment_json['title']
                    else:
                        this_comment = {}
                        this_comment['id'] = comment_id
                        this_comment['collection'] = 'medline'
                    updated_comments.append(this_comment)
                self.requested_fields['comments_'+comment_type] = updated_comments

    def saveDoc(self):

        object = {}
        object['id'] = self.doc_id
        object['collection'] = self.collection
        object['hl_fields'] = self.hl_fields
        object['requested_fields'] = self.requested_fields
        object['hl_entities'] = self.hl_entities

        return object

    def generateJson(self):
        ''' Build the json object'''

        # If the document has not been processed, generates them
        if not hasattr(self, "stats"):
            self.processDocument()

        self.final_doc = {}

        # Basic json information
        self.final_doc['id'] = self.doc_id
        self.final_doc['collection'] = self.collection
        self.final_doc['score'] = self.final_score
        self.final_doc['rank'] = self.rank

        # Correct date
        for field in self.requested_fields:
            if field == "date":
                self.requested_fields[field] = int(self.requested_fields[field])

        # Requested json fields
        self.final_doc.update(self.requested_fields)

        # Add statistics
        self.final_doc['details'] = self.stats.getJson()

        # Add snipets
        self.final_doc['evidences'] = self.cleaned_snippets

    def getJson(self):
        ''' Return the document as a json '''
        return self.final_doc