"""
WSGI config for lead_routing_project project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/3.1/howto/deployment/wsgi/
"""

import os
import sys
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'lead_routing_project.settings')
sys.path.append('/home/leadscor/public_html/') #Add this also
application = get_wsgi_application()
