"""The web app for learners (and parents and teachers): the same Svelte app as the desktop and
mobile builds, served at /learn and installable as a PWA. Built by `npm run build:web` in client/.

The shell is the same for everyone and signs in inside the app with a device token (as the apps
do), so an installed PWA never leaves its scope for /login."""

no_cache = 1


def get_context(context):
	context.no_breadcrumbs = True
	return context
