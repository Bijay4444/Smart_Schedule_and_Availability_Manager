Settings
When it comes to Django settings, we tend to follow the folder structure from cookiecutter-django, with few adjustments:

We separate Django specific settings from other settings.
Everything should be included in base.py.
There should be nothing that's only included in production.py.
Things that need to only work in production are controlled via environment variables.
Here's the folder structure of our Styleguide-Example project:

config
├── __init__.py
├── django
│   ├── __init__.py
│   ├── base.py
│   ├── local.py
│   ├── production.py
│   └── test.py
├── settings
│   ├── __init__.py
│   ├── celery.py
│   ├── cors.py
│   ├── sentry.py
│   └── sessions.py
├── urls.py
├── env.py
└── wsgi.py
├── asgi.py
In config/django, we put everything that's Django related:

base.py contains most of the settings & imports everything else from config/settings
production.py imports from base.py and then overwrites some specific settings for production.
test.py imports from base.py and then overwrites some specific settings for running tests.
This should be used as the settings module in pytest.ini.
local.py imports from base.py and can overwrite some specific settings for local development.
If you want to use that, point to local in manage.py. Otherwise stick with base.py
In config/settings, we put everything else:

Celery configuration.
3rd party configurations.
etc.
This gives you a nice separation of modules.

Additionally, we usually have config/env.py with the following code:

import environ

env = environ.Env()
And then, whenever we need to read something from the environment, we import like that:

from config.env import env
Usually, at the end of the base.py module, we import everything from config/settings:

from config.settings.cors import *  # noqa
from config.settings.sessions import *  # noqa
from config.settings.celery import *  # noqa
from config.settings.sentry import *  # noqa
Prefixing environment variables with DJANGO_
In a lot of examples, you'll see that environment variables are usually prefixed with DJANGO_. This is very helpful when there are other applications alongside your Django app that run on the same environment. In that case, prefixing the environment variables with DJANGO_ helps you to differ which are the environment variables specific to your Django app.

In HackSoft we do not ususally have several apps running on the same environment. So, we tend to prefix with DJANGO_ only the Django specific environments & anything else.

For example, we would have DJANGO_SETTINGS_MODULE, DJANGO_DEBUG, DJANGO_ALLOWED_HOSTS, DJANGO_CORS_ORIGIN_WHITELIST prefixed. We would have AWS_SECRET_KEY, CELERY_BROKER_URL, EMAILS_ENABLED not prefixed.

This is mostly up to personal preference. Just make sure you are consistent with that.

Integrations
Since everything should be imported in base.py, but sometimes we don't want to configure a certain integration for local development, we derived the following approach:

Integration-specific settings are placed in config/settings/some_integration.py
There's always a boolean setting called USE_SOME_INTEGRATION, which reads from the environment & defaults to False.
If the value is True, then proceed reading other settings & failing if things are not present in the environment.
For example, lets take a look at config/settings/sentry.py:

from config.env import env

SENTRY_DSN = env('SENTRY_DSN', default='')

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    # ... we proceed with sentry settings here ...
    # View the full file here - https://github.com/HackSoftware/Styleguide-Example/blob/master/config/settings/sentry.py
Reading from .env
Having a local .env is a nice way of providing values for your settings.

And the good thing is, django-environ provides you with a way to do that:

# That's in the beginning of base.py

import os

from config.env import env, environ

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = environ.Path(__file__) - 3

env.read_env(os.path.join(BASE_DIR, ".env"))
Now you can have a .env (but it's not required) file in your project root & place values for your settings there.

There are 2 things worth mentioning here:

Don't put .env in your source control, since this will leak credentials.
Rather put an .env.example with empty values for everything, so new developers can figure out what's being used.
Errors & Exception Handling
👀 If you want the code, hop to the Styleguide-Example project - https://github.com/HackSoftware/Styleguide-Example/blob/master/styleguide_example/api/exception_handlers.py

Errors & exception handling is a big topic & quite often - the details are specific for a given project.

That's why we'll split things into two - general guidelines, followed by some specific approaches for error handling.

Our general guidelines are:

Know how exception handling works (we'll give context for Django Rest Framework).
Describe how your API errors are going to look like.
Know how to change the default exception handling behavior.
Followed by some specific approaches:

Use DRF's default exceptions, with very little modifications.
HackSoft's proposed approach.
If you are looking for a standard way to structure your error responses, check RFC7807 - https://datatracker.ietf.org/doc/html/rfc7807 (as proposed here - #133)

How exception handling works (in the context of DRF)
DRF has an excellent guide on how exceptions are being handled, so make sure to read it first - https://www.django-rest-framework.org/api-guide/exceptions/

Additionally, here's a neat diagram with an overview of the process:

Exception handler (1)

Basically, if the exception handler cannot handle the given exception & returns None, this will result in an unhandled exception & a 500 Server Error. This is often good, because you won't be silencing errors, that you need to pay attention to.

Now, there are some quirks, that we need to pay attention to.

DRF's ValidationError
For example, if we simply raise a rest_framework.exceptions.ValidationError like that:

from rest_framework import exceptions


def some_service():
    raise exceptions.ValidationError("Some message")
The response payload is going to look like this:

["Some message"]
This looks strange, because if we do it like this:

from rest_framework import exceptions


def some_service():
    raise exceptions.ValidationError({"error": "Some message"})
The response payload is going to look like this:

{
  "error": "Some message"
}
That's basically what we passed as the detail of the ValidationError. But it's a different data structure from the initial array.

Now, if we decide to raise another of the DRF's built-in exceptions:

from rest_framework import exceptions


def some_service():
    raise exceptions.NotFound()
The response payload is going to look like this:

{
  "detail": "Not found."
}
That's entirely different from what we saw as behavior from the ValidationError and this might cause problems.

So far, the default DRF behavior can get us:

An array.
A dictionary.
A specific {"detail": "something"} result.
So if we need to use the default DRF behavior, we need to take care of this inconsistency.

Django's ValidationError
Now, DRF's default exception handling is not playing nice with Django's ValidationError.

This piece of code:

from django.core.exceptions import ValidationError as DjangoValidationError


def some_service():
    raise DjangoValidationError("Some error message")
Will result in an unhandled exception, causing 500 Server Error.

This will also happen if this ValidationError comes from model validation, for example:

def some_service():
    user = BaseUser()
    user.full_clean()  # Throws ValidationError
    user.save()
This will also result in 500 Server Error.

If we want to start handling this, as if it was rest_framework.exceptions.ValidationError, we need to roll-out our own custom exception handler:

from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework.views import exception_handler
from rest_framework.serializers import as_serializer_error
from rest_framework import exceptions


def custom_exception_handler(exc, ctx):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(as_serializer_error(exc))

    response = exception_handler(exc, ctx)

    # If unexpected error occurs (server error, etc.)
    if response is None:
        return response

    return response
This is basically the default implementation, with the addition of this piece of code:

if isinstance(exc, DjangoValidationError):
    exc = exceptions.ValidationError(as_serializer_error(exc))
Since we need to map between django.core.exceptions.ValidationError and rest_framework.exceptions.ValidationError, we are using DRF's as_serializer_error, which is used internally in the serializers, just for that.

With that, we can now have Django's ValidationError playing nice with DRF's exception handler.