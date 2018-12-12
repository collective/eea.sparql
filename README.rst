==========
EEA Sparql
==========
.. image:: https://ci.eionet.europa.eu/buildStatus/icon?job=eea/eea.sparql/develop
  :target: https://ci.eionet.europa.eu/job/eea/job/eea.sparql/job/develop/display/redirect
  :alt: develop
.. image:: https://ci.eionet.europa.eu/buildStatus/icon?job=eea/eea.sparql/master
  :target: https://ci.eionet.europa.eu/job/eea/job/eea.sparql/job/master/display/redirect
  :alt: master

EEA Sparql is a plone product for fetching data from Linked open data servers
(sparql endpoints).


.. contents::


Introduction
============

It is simple to use, you only have to specify the sparql endpoint url and the
sparql query.
The results will be converted in an exhibit json, what can easily be reused
(ex. by eea.daviz).


Main features
=============

The main features are:

1. create sparql queries
2. create sparql bookmark folders, sparql queries are created automatically,
   and can be synchronized manually or automatically (with a cronjob).
   If a query is changed, a new version of the object is created,
   so older ones are not lost.
3. results are downloadable in various formats:
   JSON, Exhibit JSON, HTML, XML, XML with Schema, CSV, TSV


Installation
============

To install eea.sparql into the global Python environment (or a workingenv),
using a traditional Zope 2 instance, you can do this:

* When you're reading this you have probably already run
  ``easy_install eea.sparql``. Find out how to install setuptools
  (and EasyInstall) here:
  http://peak.telecommunity.com/DevCenter/EasyInstall

* If you are using Zope 2.9 (not 2.10), get `pythonproducts`_ and install it
  via::

      python setup.py install --home /path/to/instance

  into your Zope instance.

* Create a file called ``eea.sparql-configure.zcml`` in the
  ``/path/to/instance/etc/package-includes`` directory.  The file
  should only contain this::

      <include package="eea.sparql" />

.. _pythonproducts: http://plone.org/products/pythonproducts


Alternatively, if you are using zc.buildout and the plone.recipe.zope2instance
recipe to manage your project, you can do this:

* Add ``eea.sparql`` to the list of eggs to install, e.g.::

    [buildout]
    eggs = eea.sparql

* Tell the plone.recipe.zope2instance recipe to install a ZCML slug::

    [instance]
    recipe = plone.recipe.zope2instance
    zcml = eea.sparql


You can skip the ZCML slug if you are going to explicitly include the package
from another package's configure.zcml file.

You will also need a worker instance to be set up. This is required for the async
update of the last working results.

* For both, normal and worker instances, the plone.app.async should be added in
  the EGG slug::

      eggs =
        ...
        plone.app.async

* For the normal instances, the plone.app.async-single_db_instance should be
  added in the ZCML slug::

      zcml =
        ...
        plone.app.async-single_db_instance

* For the worker instances, the plone.app.async-single_db_worker should be
  added in the ZCML slug::

      zcml =
        ...
        plone.app.async-single_db_worker

* Re-run buildout, e.g. with::

    $ ./bin/buildout

Dependecies
===========

* Products.ZSPARQLMethod
* eea.versions
* plone.app.async
* eea.cache 7.0+ (optional)

Source code
===========

Latest source code (Plone 4 compatible):
- `Plone Collective on Github <https://github.com/collective/eea.sparql>`_
- `EEA on Github <https://github.com/eea/eea.sparql>`_


Copyright and license
=====================

The Initial Owner of the Original Code is European Environment Agency (EEA).
All Rights Reserved.

The EEA Sparql (the Original Code) is free software;
you can redistribute it and/or modify it under the terms of the GNU
General Public License as published by the Free Software Foundation;
either version 2 of the License, or (at your option) any later
version.

More details under docs/License.txt


Links
=====

1. http://en.wikipedia.org/wiki/SPARQL
2. http://sparql.org/
3. http://www.w3.org/TR/rdf-sparql-query/


Funding
=======

EEA_ - European Environment Agency (EU)

.. _EEA: https://www.eea.europa.eu/
