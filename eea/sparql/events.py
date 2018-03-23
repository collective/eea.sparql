""" Sparql events
"""

from zope.interface import implements
from zope.component.interfaces import ObjectEvent
from eea.sparql.interfaces import ISparqlBookmarksFolderAdded

class SparqlBookmarksFolderAdded(ObjectEvent):
    """SparqlBookmarksFolder was added
    """
    implements(ISparqlBookmarksFolderAdded)