""" sparql
"""
import cgi
import contextlib
import csv
import json
import logging
import urllib
import urllib2
from time import time
import re
import DateTime

from plone import api
from Products.CMFCore.utils import getToolByName
from Products.Five import BrowserView
from Products.ZSPARQLMethod.Method import interpolate_query
from Products.ZSPARQLMethod.Method import interpolate_query_html
from Products.ZSPARQLMethod.Method import map_arg_values
from Products.ZSPARQLMethod.Method import parse_arg_spec
from Products.ZSPARQLMethod.Method import query_and_get_result
from Products.ZSPARQLMethod.Method import run_with_timeout
from eea.sparql.converter.sparql2json import sortProperties
from eea.sparql.converter.sparql2json import sparql2json
from eea.versions.interfaces import IGetVersions

logger = logging.getLogger('eea.sparql')


class ExcelTSV(csv.excel):
    """ CSV Tab Separated Dialect
    """
    delimiter = '\t'
csv.register_dialect("excel.tsv", ExcelTSV)


class Sparql(BrowserView):
    """Sparql view"""

    def getArgumentMap(self):
        """Returns the arguments and their values"""
        arg_dict = {}
        for k in self.context.arg_spec:
            arg = k['name'].split(':')[0]
            arg_dict[arg] = self.request.get(arg, None)
        return arg_dict


    def getArguments(self):
        """Returns the SPARQL arguments as text"""
        value = ""
        for k in self.context.arg_spec:
            arg = k['name'].split(':')[0]
            val = self.request.get(arg, None)
            if val:
                value += '%s=%s&' % (arg, urllib.quote(val))
        return value[:-1]

    def getQueryMap(self):
        """Returns the SPARQL arguments and their queries"""
        query_dict = {}
        for k in self.context.arg_spec:
            arg = k['name'].split(':')[0]
            query = ' '.join(k['query'])
            query_dict[arg] = query
        return query_dict

    def hasResults(self, argument=None):
        """Tests whether the query has results or not"""
        if self.getQueryResults(argument):
            return True
        return False

    def getQueryResults(self, argument=None):
        """Returns the results for the arguments's query"""
        results = []
        if argument != None:
            arg_query = self.getQueryMap()[argument]
            query_args = (self.context.endpoint_url, arg_query)
            data = run_with_timeout(10, query_and_get_result, *query_args)
            if 'result' in data:
                return data['result']['rows']
        return results

    def getLastQueryRunTime(self):
        """ Parses the history and returns the last entry when
            the query has run.
        """
        rt = getToolByName(self.context, "portal_repository")
        if not rt.isVersionable(self.context):
            return {}

        try:
            history = rt.getHistoryMetadata(self.context)
            latest = history.getLength(countPurged=False) - 1
            version = history.retrieve(latest, countPurged=False)
            return version.get("metadata", {}).get("sys_metadata", {})
        except Exception as err:
            logger.warn(err)
            return {}

    def test_query(self):
        """test query"""
        arg_string = ' '.join([arg['name'] for arg in self.context.arg_spec])
        arg_spec = parse_arg_spec(arg_string)
        missing, arg_values = map_arg_values(arg_spec, self.request.form)
        error = None

        if missing:
            # missing argument
            data = None
            dt = 0

        else:
            t0 = time()

            res, error = {}, None
            try:
                res = self.context.execute(**arg_values)
            except Exception, err:
                import traceback
                logger.exception(err)
                error = traceback.format_exc()
            data = res.get('result')
            error = error or res.get('exception')

            dt = time() - t0

        options = {
            'query': interpolate_query_html(self.context.query, arg_values),
            'query_with_comments': interpolate_query_html(
                self.context.query_with_comments, arg_values),
            'data': data,
            'duration': dt,
            'arg_spec': arg_spec,
            'error': error,
        }
        return options

    def json(self, **kwargs):
        """json"""
        data = self.context.execute_query(self.getArgumentMap())

        column_types = kwargs.get('column_types')
        annotations = kwargs.get('annotations')
        try:
            return sortProperties(json.dumps(
                sparql2json(data,
                            column_types=column_types,
                            annotations=annotations)
            ))
        except KeyError, err:
            logger.warn(err)

    def sparql2exhibit(self):
        """ Download sparql results as Exhibit JSON
        """
        try:
            data = sparql2json(self.context.execute_query(
                self.getArgumentMap()))
        except Exception, err:
            logger.exception(err)
            data = {'properties':{}, 'items':{}}

        self.request.response.setHeader(
            'Content-Type', 'application/json')
        self.request.response.setHeader(
            'Content-Disposition',
            'attachment; filename="%s.exhibit.json"' % self.context.getId())
        return sortProperties(json.dumps(data))

    def sparql2html(self):
        """ Download sparql results as HTML
        """
        if not self.getExportStatus():
            self.request.response.setStatus(500)
            return 'Error: %s' % self.context.exportStatusMessage

        try:
            data = sparql2json(self.context.execute_query(
                self.getArgumentMap()))
        except Exception, err:
            data = {'properties':{}, 'items':{}}
            logger.exception(err)


        result = []
        result.append(u"<style type='text/css'>")
        result.append(u"table {border-collapse: collapse }")
        result.append(u"th, td {border:1px solid black}")
        result.append(u"</style>")
        result.append(u"<table>")
        result.append(u"\t<tr>")

        properties = []
        def_order = 0
        for key, item in data['properties'].items():
            prop = []
            prop.append(item.get('order', def_order))
            prop.append(key)
            prop.append(item['valueType'])
            properties.append(prop)
            def_order += 1
        properties.sort()

        for col in properties:
            result.append(u"\t\t<th>" + col[1] + u"</th>")
        result.append(u"\t</tr>")
        for row in data['items']:
            result.append(u"\t<tr>")
            for col in properties:
                result.append(u"\t\t<td>" + unicode(row[col[1]]) + "</td>")
            result.append(u"\t</tr>")
        result.append(u"</table>")
        return '\n'.join(result)

    def sparql2csv(self, dialect='excel'):
        """ Download sparql results as Comma Separated File
        """
        if not self.getExportStatus():
            self.request.response.setStatus(500)
            return 'Error: %s' % self.context.exportStatusMessage

        try:
            data = sparql2json(self.context.execute_query(
                self.getArgumentMap()))
        except Exception, err:
            data = {'properties':{}, 'items':{}}
            logger.exception(err)

        if dialect == 'excel':
            self.request.response.setHeader(
                'Content-Type', 'application/csv')
            self.request.response.setHeader(
                'Content-Disposition',
                'attachment; filename="%s.csv"' % self.context.getId())
        else:
            self.request.response.setHeader(
                'Content-Type', 'application/tsv')
            self.request.response.setHeader(
                'Content-Disposition',
                'attachment; filename="%s.tsv"' % self.context.getId())

        writter = csv.writer(self.request.response, dialect=dialect)
        row = []

        properties = []
        def_order = 0
        for key, item in data['properties'].items():
            prop = []
            prop.append(item.get('order', def_order))
            prop.append(key)
            prop.append(item['valueType'])
            properties.append(prop)
            def_order += 1
        properties.sort()

        headers = []
        for prop in properties:
            headers.append(prop[1])

        for col in headers:
            header = '%s:%s' % (col, data['properties'][col]['valueType'])
            row.append(header)
        writter.writerow(row)
        for item in data['items']:
            row = []
            for col in headers:
                row.append(unicode(item[col]).encode('utf'))
            writter.writerow(row)

        return ''


    def sparqlTriggerAsync(self, cached_data):
        """ Verify if cached data exists, if not trigger async job
        """
        if not cached_data or (cached_data and not cached_data.get_size()):
            self.context.last_scheduled_at = DateTime.DateTime()
            self.context._updateOtherCachedFormats(
                self.context.last_scheduled_at,
                self.context.endpoint_url,
                self.context.query)
            api.portal.show_message(
                message="The data will be updated shortly. Please retry later.",
                request=self.request)
            return self.request.response.redirect(self.context.absolute_url())


    def sparql2tsv(self, dialect='excel.tsv'):
        """ Download sparql results as Tab Separated File
        """
        return self.sparql2csv(dialect=dialect)

    def sparql2json(self):
        """ Download sparql results as JSON
        """
        self.request.response.setHeader(
            'Content-Type', 'application/json')
        self.request.response.setHeader(
            'Content-Disposition',
            'attachment; filename="%s.json"' % self.context.getId())

        cached_json = self.context.getSparql_results_cached_json()
        self.sparqlTriggerAsync(cached_json)

        return self.context.getSparql_results_cached_json()

    def sparql2xml(self):
        """ Download sparql results as XML
        """
        self.request.response.setHeader(
            'Content-Type', 'application/xml')
        self.request.response.setHeader(
            'Content-Disposition',
                'attachment; filename="%s.xml"' % self.context.getId())

        cached_xml = self.context.getSparql_results_cached_xml()
        self.sparqlTriggerAsync(cached_xml)

        return self.context.getSparql_results_cached_xml()

    def sparql2xmlWithSchema(self):
        """ Download sparql results as XML with schema
        """
        self.request.response.setHeader(
            'Content-Type', 'application/xml')
        self.request.response.setHeader(
            'Content-Disposition',
                'attachment; filename="%s.schema.xml"' % self.context.getId())

        cached_xml_schema = self.context.getSparql_results_cached_xmlschema()
        self.sparqlTriggerAsync(cached_xml_schema)

        return self.context.getSparql_results_cached_xmlschema()

    def sparql2response(self, headers=None):
        """ Write
        """
        endpoint = self.context.endpoint_url
        url_protocol = endpoint.split('://')
        if len(url_protocol) < 2:
            endpoint = "http://" + endpoint
        query = 'query=%s' % urllib.quote(self.context.query)
        request = urllib2.Request(endpoint, query, headers or {})
        results = ""
        timeout = max(getattr(self.context, 'timeout', 10), 10)
        try:
            with contextlib.closing(urllib2.urlopen(
                request, timeout=timeout)) as conn:
                for data in conn:
                    self.request.response.write(data)
        except Exception, err:
            logger.exception(err)
        return results

    def isDavizInstalled(self):
        """ Check if Daviz is installed
        """
        has_daviz = False
        try:
            from eea.daviz import interfaces
            has_daviz = bool(interfaces)

        except ImportError:
            has_daviz = False

        return has_daviz

    def relatedItems(self):
        """ Items what are back related to this query
        """
        return json.dumps([[x.title, x.absolute_url()]
                            for x in self.context.getBRefs('relatesTo') if x])

    def getExportStatus(self):
        """
        """
        if not getattr(self.context, 'exportWorks', True):
            return False
        return True


class SparqlBookmarksFolder(Sparql):
    """SparqlBookmarksFolder view"""

    def getBookmarks(self):
        """Get list of bookmarks and check if needs to be updated"""
        results = self.test_query()
        results_data = results.get('data', {})
        bookmarks = {}
        bookmarks['data'] = []
        bookmarks['arg_spec'] = results['arg_spec']
        bookmarks['error'] = results['error']
        bookmarks['duration'] = results['duration']
        query_endpoint = self.context.endpoint_url
        if results_data is not None:
            queries = results_data.get('rows', [])
            for query in queries:
                query_details = {}
                query_details['name'] = query[0].value
                query_details['sparql'] = query[2].value
                query_details['bookmark'] = query[1].value
                query_details['status'] = self.context.checkQuery(
                                            query_details['name'],
                                            query_endpoint,
                                            query_details['sparql'])
                bookmarks['data'].append(query_details)
        return bookmarks

    def addOrUpdateQuery(self):
        """Add or Update the Current Query"""
        ob = self.context.addOrUpdateQuery(self.request['title'],
                 self.context.endpoint_url,
                 self.request['query'])
        self.request.response.redirect(ob.absolute_url() + "/@@view")

    def syncQueries(self):
        """Synchronize all Queries"""
        self.context.syncQueries()
        self.request.response.redirect(self.context.absolute_url() + "/@@view")

    def getVisualizations(self, title):
        """ Get Daviz Visualizations for sparql object
        """
        ob = None
        for sparql in self.context.values():
            if sparql.title == title:
                ob = IGetVersions(sparql).latest_version()
                break
        if not ob:
            return []

        return ob.getBRefs('relatesTo')

    def createVisualization(self):
        """ Create visualization with datasource
        """
        ob = self.context.findQuery(self.request['title'])
        if ob:
            self.request.response.redirect(ob.absolute_url() +
                "/daviz-create-new.html")


class SparqlBookmarkFoldersSync(BrowserView):
    """ Sync all Bookmark Folders """

    def __call__(self):
        catalog = getToolByName(self, 'portal_catalog')
        brains = catalog.searchResults(portal_type='SparqlBookmarksFolder')
        for brain in brains:
            try:
                brain.getObject().syncQueries()
            except Exception, err:
                logger.exception(err)
        return "Sync done"


class QuickPreview(BrowserView):
    """ Quick Preview For Query
    """

    def preview(self):
        """preview"""
        tmp_query = self.request.get("sparql_query", "")
        tmp_query = "\n".join(x for x in tmp_query.splitlines()
                         if not x.strip().startswith("#"))
        tmp_arg_spec = self.request.get("arg_spec", "")
        tmp_endpoint = self.request.get("endpoint", "")
        tmp_timeout = int(self.request.get("timeout", "0"))

        arg_spec = parse_arg_spec(tmp_arg_spec)
        missing, arg_values = map_arg_values(arg_spec, self.request.form)
        error = None
        if missing:
            error = ""
            for missing_arg in missing:
                error = error + "<div>Argument '%s' missing</div>" % missing_arg
        else:
            result = []
            data = []
            error = None
            try:
                m = re.search(r"limit\s(\d+)", tmp_query, re.IGNORECASE)
                if m:
                    tmp_query = tmp_query[:m.start(1)]+'10'+tmp_query[m.end(1):]
                else:
                    tmp_query = tmp_query + " LIMIT 5"
                cooked_query = interpolate_query(tmp_query, arg_values)
                args = (tmp_endpoint, cooked_query)
                result, error = {}, None
                result = run_with_timeout(tmp_timeout,
                                            query_and_get_result,
                                            *args)
                data = result.get('result', {})
                error = error or result.get('exception')
            except Exception:
                import traceback
                error = traceback.format_exc()

        if error:
            return "<code class='sparql-error'><pre> %s </pre></code>" % error

        result = [u"<table class='sparql-results'>", u"<thead>", u"<tr>"]
        for var_name in data.get('var_names', []):
            result.append(u"<th> %s </th>" %var_name)
        result.append(u"</tr>")
        result.append(u"</thead>")
        result.append(u"<tbody>")
        for row in data.get('rows', []):
            result.append(u"<tr class='row_0'>")
            for value in row:
                try:
                    result.append(u"<td> %s </td>" %cgi.escape(value.n3()))
                except Exception, err:
                    logger.debug(err)
                    result.append(u"<td> %s </td>" %value)
            result.append(u"</tr>")
        result.append(u"</tbody>")
        result.append(u"</table>")
        return "\n".join(result)
