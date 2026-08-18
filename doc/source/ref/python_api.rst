.. _ref_python_api:

Python API reference
====================

The supported Python API is what the top-level :mod:`fusesoc` package
exports. See :ref:`ug_library_usage` for a usage-oriented introduction.

Facade
------

.. autoclass:: fusesoc.Fusesoc
   :members:

Configuration
-------------

.. autoclass:: fusesoc.Config
   :members: resolve_path, global_config_path, from_dict, add_library, record_library

Flags
-----

.. autoclass:: fusesoc.Flags
   :members: from_mapping, from_cli_strings, replace, with_core_defaults

Libraries
---------

.. autoclass:: fusesoc.Library
   :members: from_uri

Core names
----------

.. autoclass:: fusesoc.Vlnv
   :members:

Exceptions
----------

.. automodule:: fusesoc.exceptions
   :members:
   :show-inheritance:
