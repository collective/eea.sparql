"""Definition of the Sparql content type
"""

import cPickle
import datetime
from random import random
import logging
import pytz
from AccessControl import ClassSecurityInfo
from AccessControl import SpecialUsers
from AccessControl import getSecurityManager
from AccessControl.Permissions import view
from AccessControl.SecurityManagement import newSecurityManager
from AccessControl.SecurityManagement import setSecurityManager
from zope.interface import implements
from zope.component import queryUtility
from zope.event import notify
import DateTime
from Products.ATContentTypes.content import schemata, base
from Products.ATContentTypes.content.folder import ATFolder
from Products.Archetypes import atapi
from Products.Archetypes.atapi import IntegerField
from Products.Archetypes.atapi import Schema
from Products.Archetypes.atapi import SelectionWidget
from Products.Archetypes.atapi import StringField, StringWidget, \
                                        BooleanWidget, BooleanField
from Products.Archetypes.atapi import TextField, TextAreaWidget
from Products.CMFCore.utils import getToolByName
from Products.CMFEditions.interfaces.IModifier import FileTooLargeToVersionError
from Products.DataGridField import DataGridField, DataGridWidget
from Products.DataGridField.Column import Column
from Products.DataGridField.LinesColumn import LinesColumn
from Products.ZSPARQLMethod.Method import ZSPARQLMethod, \
                                        interpolate_query, \
                                        run_with_timeout, \
                                        parse_arg_spec, \
                                        query_and_get_result, \
                                        raw_query_and_get_result, \
                                        map_arg_values, QueryTimeout
from ZODB.POSException import POSKeyError
from eea.sparql.cache import ramcache, cacheSparqlKey, cacheSparqlMethodKey
from eea.sparql.config import PROJECTNAME
from eea.sparql.events import SparqlBookmarksFolderAdded
from eea.sparql.interfaces import ISparql, ISparqlBookmarksFolder
from eea.versions import versions
from eea.versions.interfaces import IVersionEnhanced, IGetVersions
from eea.sparql.async import IAsyncService
from plone.app.blob.field import BlobField
from eea.sparql.converter.sparql2json import sparql2json
logger = logging.getLogger("eea.sparql")

RESULTS_TYPES = {
                 'xml' : "application/sparql-results+xml",
                 'xmlschema' : "application/x-ms-access-export+xml",
                 'json' : "application/sparql-results+json"
                 }

SparqlBaseSchema = atapi.Schema((
    StringField(
        name='endpoint_url',
        widget=StringWidget(
            label="Sparql endpoint URL",
        ),
        validators=('isURL',),
        required=1
    ),
    IntegerField(
        name='timeout',
        widget=SelectionWidget(
            label="Timeout (seconds)",
        ),
        default=10,
        required=1,
        vocabulary=['10', '20', '30', '40', '50', '60', '300', '600'],
        accessor='getTimeout',
        edit_accessor='getTimeout',
        mutator='setTimeout'
    ),
    DataGridField(
        name='arg_spec',
        widget=DataGridWidget(
            label="Arguments",
            description="""Provide names, types and queries for the arguments.
                    Names and types are mandatory, but you can leave the
                    query field empty.
                    Details and a full tutorial on how to work with
                    arguments <a
                    href="++resource++eea.sparql.documentation/api/index.html"
                    title="tutorial">here.</a>
                        """,
            auto_insert=False,
            i18n_domain='eea',
            columns={
                'name': Column("Name"),
                'query': LinesColumn("Query")
            },
            helper_js=('++resource++eea.sparql.datasource.js',
                       'datagridwidget.js',),
            helper_css=('++resource++eea.sparql.datasource.css',
                        'datagridwidget.css')
            ),
        columns=("name", "query")
    ),
    TextField(
        name='sparql_query',
        default_content_type='text/plain',
        allowable_content_types=('text/plain',),

        widget=TextAreaWidget(
            macro="sparql_textfield_with_preview",
            helper_js=("sparql_textfield_with_preview.js",),
            helper_css=("sparql_textfield_with_preview.css",),
            label="Query",
        ),
        required=1,
        validators=('isSparqlOverLimit',)
    ),
    BooleanField(
        name='sparql_static',
        widget=BooleanWidget(
            label='Static query',
            description='The data will be fetched only once',
            visible={'edit':'invisible', 'view':'invisible'}
        ),
        default=False,
        required=0
    ),
    TextField(
        name='sparql_results',
        widget=TextAreaWidget(
            label="Results",
            visible={'edit':'invisible', 'view':'invisible'}
        ),
        required=0,

    ),
    BlobField(
        name='sparql_results_cached',
        widget=TextAreaWidget(
            label="Results",
            visible={'edit':'invisible', 'view':'invisible'}
        ),
        required=0,
    ),
    BlobField(
        name='sparql_results_cached_json',
        widget=TextAreaWidget(
            label="Results",
            visible={'edit':'invisible', 'view':'invisible'}
        ),
        required=0,
    ),
    BlobField(
        name='sparql_results_cached_xml',
        widget=TextAreaWidget(
            label="Results",
            visible={'edit':'invisible', 'view':'invisible'}
        ),
        required=0,
    ),
    BlobField(
        name='sparql_results_cached_xmlschema',
        widget=TextAreaWidget(
            label="Results",
            visible={'edit':'invisible', 'view':'invisible'}
        ),
        required=0,
    ),
    StringField(
        name='refresh_rate',
        widget=SelectionWidget(
            label="Refresh the results",
        ),
        default='Weekly',
        required=1,
        vocabulary=['Once', 'Hourly', 'Daily', 'Weekly'],
    ),
))

SparqlSchema = getattr(base.ATCTContent, 'schema', Schema(())).copy() + \
        SparqlBaseSchema.copy()

SparqlSchema['title'].storage = atapi.AnnotationStorage()
SparqlSchema['description'].storage = atapi.AnnotationStorage()

schemata.finalizeATCTSchema(SparqlSchema, moveDiscussion=False)

SparqlBookmarksFolderSchema = getattr(ATFolder, 'schema', Schema(())).copy() + \
        SparqlBaseSchema.copy()
SparqlBookmarksFolderSchema['sparql_query'].widget.description = \
        'The query should return label, bookmark url, query'
SparqlBookmarksFolderSchema['sparql_static'].widget.visible['edit'] = \
        'invisible'

class Sparql(base.ATCTContent, ZSPARQLMethod):
    """Sparql"""
    implements(ISparql, IVersionEnhanced)

    meta_type = "Sparql"
    schema = SparqlSchema

    title = atapi.ATFieldProperty('title')
    description = atapi.ATFieldProperty('description')

    security = ClassSecurityInfo()

    security.declarePublic('index_html')
    def index_html(self, REQUEST=None, **kwargs):
        """index_html"""
        return self.REQUEST.response.redirect(self.absolute_url()+"/@@view")

    @property
    def query(self):
        """query"""
        return "\n".join(x for x in self.sparql_query().splitlines()
                         if not x.strip().startswith("#"))

    @property
    def query_with_comments(self):
        """query"""
        return self.sparql_query()

    security.declarePublic("execute_query")
    @ramcache(cacheSparqlKey, dependencies=['eea.sparql'])
    def execute_query(self, args=None):
        """execute query"""
        arg_string = ' '.join([arg['name'] for arg in self.arg_spec])
        arg_spec = parse_arg_spec(arg_string)
        arg_values = map_arg_values(arg_spec, args)[1]
        return self.execute(**self.map_arguments(**arg_values))

    security.declarePublic("getTimeout")
    def getTimeout(self):
        """timeout"""
        return str(self.timeout)

    security.declarePublic("setTimeout")
    def setTimeout(self, value):
        """timeout"""
        try:
            self.timeout = int(value)
        except Exception:
            self.timeout = 10

    @ramcache(cacheSparqlMethodKey, dependencies=['eea.sparql'])
    def _getCachedSparqlResults(self):
        """
        :return: Cached Sparql results
        :rtype: object
        """
        empty_result = {"result": {"rows": "", "var_names": "",
                                   "has_result": ""}}
        try:
            data = self.getSparql_results_cached().data
        # 69841 take into account missing blobs
        except POSKeyError:
            return empty_result
        # 69841 make sure the data returned can be pickled
        try:
            return cPickle.loads(data)
        except cPickle.UnpicklingError:
            return empty_result

    security.declarePublic("getSparqlCacheResults")
    def getSparqlCacheResults(self):
        """
        :return: Sparql results
        :rtype: object
        """
        if getattr(self, 'sparql_results_are_cached', None):
            return self._getCachedSparqlResults()
        field = self.getSparql_results_cached()
        empty_result = {"result": {"rows": "", "var_names": "",
                                   "has_result": ""}}
        return cPickle.loads(field.data) if field and field.data else \
            empty_result


    security.declareProtected(view, 'setSparqlCacheResults')
    def setSparqlCacheResults(self, result):
        """ Set Sparql Cache results
        """
        self.updateExportStatus(result)
        self.sparql_results_are_cached = True
        self.setSparql_results_cached(cPickle.dumps(result))

    security.declareProtected(view, 'invalidateSparqlCacheResults')
    def invalidateSparqlCacheResults(self):
        """ Invalidate sparql results
        """
        self.sparql_results_are_cached = False
        self.setSparql_results_cached("")

    security.declareProtected(view, 'invalidateWorkingResult')
    def invalidateWorkingResult(self):
        """ invalidate working results"""
        self.setSparql_results("")
        self.invalidateSparqlCacheResults()

        pr = getToolByName(self, 'portal_repository')
        comment = "Invalidated last working result"
        comment = comment.encode('utf')
        try:
            pr.save(obj=self, comment=comment)
        except FileTooLargeToVersionError:
            commands = view.getCommandSet('plone')
            commands.issuePortalMessage(
                """Changes Saved. Versioning for this file
                   has been disabled because it is too large.""",
                msgtype="warn")

        async_service = queryUtility(IAsyncService)
        if async_service is None:
            logger.warn(
                "Can't invalidateWorkingResult. plone.app.async NOT installed!")
            return

        self.scheduled_at = DateTime.DateTime()
        async_queue = async_service.getQueues()['']
        async_service.queueJobInQueue(
            async_queue, ('sparql',),
            async_updateLastWorkingResults,
            self,
            scheduled_at=self.scheduled_at,
            bookmarks_folder_added=False
        )

    def _updateOtherCachedFormats(self, scheduled_at, endpoint, query):
        """ Run and store queries in sparql endpoints for xml, xmlschema, json
        """

        async_service = queryUtility(IAsyncService)
        if async_service is None:
            logger.warn(
                "Can't invalidateWorkingResult. plone.app.async NOT installed!")
            return

        async_queue = async_service.getQueues()['']
        delay = datetime.datetime.now(pytz.UTC)

        for _type, accept in RESULTS_TYPES.items():
            delay = delay + datetime.timedelta(minutes=5)
            async_service.queueJobInQueueWithDelay(
                None, delay,
                async_queue, ('sparql',),
                async_updateOtherCachedFormats,
                self,
                scheduled_at, endpoint, query, _type, accept
            )

    security.declareProtected(view, 'updateLastWorkingResults')
    def updateLastWorkingResults(self, **arg_values):
        """ update cached last working results of a query (json exhibit)
        """

        cached_result = self.getSparqlCacheResults()
        cooked_query = interpolate_query(self.query, arg_values)

        args = (self.endpoint_url, cooked_query)
        try:
            new_result = run_with_timeout(
                max(getattr(self, 'timeout', 10), 10),
                query_and_get_result,
                *args)
        except QueryTimeout:
            new_result = {'exception': "query has ran - an timeout has"
                                       " been received"}
        force_save = False

        if new_result.get("result", {}) != {}:
            if new_result != cached_result:
                if new_result.get("result", {}).get("rows", {}):
                    force_save = True
                else:
                    if not cached_result.get('result', {}).get('rows', {}):
                        force_save = True

        pr = getToolByName(self, 'portal_repository')
        comment = "query has run - no result changes"

        if force_save:
            self.setSparqlCacheResults(new_result)
            self._updateOtherCachedFormats(self.last_scheduled_at,
                self.endpoint_url, cooked_query)

            new_sparql_results = []
            rows = new_result.get('result', {}).get('rows', {})
            if rows:
                for row in rows:
                    for val in row:
                        new_sparql_results.append(unicode(val) + " | ")
                new_sparql_results[-1] = new_sparql_results[-1][0:-3]
            new_sparql_results_str = "".join(new_sparql_results) + "\n"
            self.setSparql_results(new_sparql_results_str)
            comment = "query has run - result changed"
        if self.portal_type in pr.getVersionableContentTypes():
            comment = comment.encode('utf')
            try:
                oldSecurityManager = getSecurityManager()
                newSecurityManager(None, SpecialUsers.system)
                pr.save(obj=self, comment=comment)
                setSecurityManager(oldSecurityManager)
            except FileTooLargeToVersionError:
                commands = view.getCommandSet('plone')
                commands.issuePortalMessage(
                    """Changes Saved. Versioning for this file
                       has been disabled because it is too large.""",
                    msgtype="warn")

        if new_result.get('exception', None):
            cached_result['exception'] = new_result['exception']
            self.setSparqlCacheResults(cached_result)

    security.declareProtected(view, 'updateExportStatus')
    def updateExportStatus(self, result):
        """ Update export status of HTML/CSV/TSV
        """
        setattr(self, 'exportWorks', True)
        try:
            setattr(self, 'exportWorks', True)
            setattr(self, 'exportStatusMessage', '')
            sparql2json(result)
        except Exception, err:
            logger.exception(err)
            setattr(self, 'exportWorks', False)
            setattr(self, 'exportStatusMessage', err)
        self._p_changed = True
        self.reindexObject()

    security.declareProtected(view, 'execute')
    def execute(self, **arg_values):
        """ override execute, if possible return the last working results
        """
        cached_result = self.getSparqlCacheResults()
        if not arg_values:
            return cached_result

        self.updateLastWorkingResults(**arg_values)
        return cached_result

    security.declareProtected(view, 'map_arguments')
    def map_arguments(self, **arg_values):
        """ overides map_arguments to match the name:type - query data model
        """
        arg_string = ' '.join([arg['name'] for arg in self.arg_spec])
        arg_spec = parse_arg_spec(arg_string)
        missing, arg_values = map_arg_values(arg_spec, arg_values)
        if missing:
            raise KeyError("Missing arguments: %r" % missing)
        else:
            return arg_values


def async_updateOtherCachedFormats(obj, scheduled_at, endpoint, query,
                                    _type, accept):
    """ Async that updates json, xml, xmlschema exports
    """

    if obj.last_scheduled_at == scheduled_at:
        timeout = max(getattr(obj, 'timeout', 10), 10)
        try:
            new_result = run_with_timeout(
                timeout,
                raw_query_and_get_result, endpoint, query, accept=accept
            )
        except QueryTimeout:
            new_result = ""
            logger.warning(
                "Query received timeout: %s with %s\n %s \n %s",
                "/".join(obj.getPhysicalPath()), _type, endpoint, query
            )
            return

        fieldName = "sparql_results_cached_" + _type
        mutator = obj.Schema().getField(fieldName).getMutator(obj)

        try:
            result = new_result['result'].read()
        except Exception:
            result = ""
            logger.warn(
                "Unable to read result from query: %s with %s\n %s \n %s",
                "/".join(obj.getPhysicalPath()), _type, endpoint, query
            )
        mutator(result)


def async_updateLastWorkingResults(obj,
                                scheduled_at,
                                bookmarks_folder_added=False):
    """ Async update last working results
    """

    if obj.scheduled_at == scheduled_at:
        obj.last_scheduled_at = scheduled_at
        obj.updateLastWorkingResults()

        refresh_rate = getattr(obj, "refresh_rate", "Weekly")
        if refresh_rate == 'Once':
            cached_result = obj.getSparqlCacheResults()
            if not cached_result.get('result', {}).get('rows', {}):
                refresh_rate = 'Hourly'
        else:
            if bookmarks_folder_added:
                notify(SparqlBookmarksFolderAdded(obj))
                bookmarks_folder_added = False

        before = datetime.datetime.now(pytz.UTC)

        delay = before + datetime.timedelta(hours=1)
        if refresh_rate == "Daily":
            delay = before + datetime.timedelta(days=1)
        if refresh_rate == "Weekly":
            delay = before + datetime.timedelta(weeks=1)
        if refresh_rate != "Once":
            async_service = queryUtility(IAsyncService)
            if async_service is None:
                logger.warn("Can't async_updateLastWorkingResults. "
                            "plone.app.async NOT installed!")
                return

            obj.scheduled_at = DateTime.DateTime()
            async_queue = async_service.getQueues()['']
            async_service.queueJobInQueueWithDelay(
                None, delay,
                async_queue, ('sparql',),
                async_updateLastWorkingResults,
                obj,
                scheduled_at=obj.scheduled_at,
                bookmarks_folder_added=bookmarks_folder_added
            )

def generateUniqueId(type_name):
    """ generateUniqueIds for sparqls
    """
    now = DateTime.DateTime()
    time = '%s.%s' % (now.strftime('%Y-%m-%d'), str(now.millis())[7:])
    rand = str(random())[2:6]
    prefix = ''
    suffix = ''

    if type_name is not None:
        prefix = type_name.replace(' ', '_') + '.'
    prefix = prefix.lower()

    return prefix + time + rand + suffix

class SparqlBookmarksFolder(ATFolder, Sparql):
    """Sparql Bookmarks Folder"""
    implements(ISparqlBookmarksFolder)
    meta_type = "SparqlBookmarksFolder"
    schema = SparqlBookmarksFolderSchema

    def checkQuery(self, title, endpoint, query):
        """Check if a query already exists
           0 - missing
           1 - exists
           2 - exists but changed"""
        found = False
        changed = True
        for sparql in self.values():
            if sparql.title == title.encode('utf8'):
                latest_sparql = IGetVersions(sparql).latest_version()
                found = True
                if latest_sparql.query_with_comments == query:
                    changed = False
                break
        if not found:
            return 0
        if not changed:
            return 1
        return 2

    def addOrUpdateQuery(self, title, endpoint, query):
        """Update an already existing query
           Create new version"""
        oldSecurityManager = getSecurityManager()
        newSecurityManager(None, SpecialUsers.system)

        ob = None

        changed = True
        for sparql in self.values():
            if sparql.title == title:
                x1 = IGetVersions(sparql)
                latest_sparql = x1.latest_version()
                ob = latest_sparql
                if latest_sparql.query_with_comments == query:
                    changed = False
                break

        if not ob:
            _id = generateUniqueId("Sparql")
            _id = self.invokeFactory(type_name="Sparql", id=_id)
            ob = self[_id]
            ob.edit(
                title=title,
                endpoint_url=endpoint,
                sparql_query=query,
            )
            ob._renameAfterCreation(check_auto_id=True)
            ob.invalidateWorkingResult()
        else:
            if changed:
                ob = versions.create_version(ob)
                ob.edit(
                    sparql_query=query,
                )
                ob.invalidateWorkingResult()

        setSecurityManager(oldSecurityManager)
        return ob

    def findQuery(self, title):
        """Find the Query in the bookmarks folder
        """
        ob = None
        for sparql in self.values():
            if sparql.title == title:
                latest_sparql = IGetVersions(sparql).latest_version()
                ob = latest_sparql
                break
        return ob

    def syncQueries(self):
        """sync all queries from bookmarks"""
        queries = self.execute().get('result', {}).get('rows', {})
        for query in queries:
            query_name = query[0].value
            query_sparql = query[2].value
            self.addOrUpdateQuery(query_name,
                     self.endpoint_url,
                     query_sparql)

atapi.registerType(Sparql, PROJECTNAME)
atapi.registerType(SparqlBookmarksFolder, PROJECTNAME)
