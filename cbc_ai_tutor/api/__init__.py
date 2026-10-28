"""HTTP API used by the CBC AI Tutor desktop and mobile apps.

Every endpoint here is a whitelisted method under ``/api/method/cbc_ai_tutor.api.*``.
The apps authenticate with ``Authorization: Bearer cbc_...`` device tokens issued by
:mod:`cbc_ai_tutor.api.auth`. Endpoints scope every read and write to the signed-in
learner, parent or teacher explicitly, so they run with ``ignore_permissions`` and
never trust a record name sent by the client without checking who owns it.
"""
