import os
from django.conf import settings

from supabase import create_client

#SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://gvtyappmanytqrvwpiqr.supabase.co")
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_KEY
#SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd2dHlhcHBtYW55dHFydndwaXFyIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NTMxMjkyMiwiZXhwIjoyMDkwODg4OTIyfQ.bR5xwS28iurjEg3nXxyJY4w5bDhxQ0bQ0Bds_8mH89c")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Vérifier les buckets
buckets = supabase.storage.list_buckets()
print("Buckets disponibles:", buckets)

# Uploader un fichier test
with open("test.txt", "w") as f:
    f.write("Hello Supabase, THIS IS A TEST!")

with open("test.txt", "rb") as f:
    supabase.storage.from_("whatsappMedia").upload("test.txt", f)

print("Fichier uploadé dans whatsappMedia !")