from django.shortcuts import render

import os
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseNotFound



@login_required
def descargar_manual_pdf(request):
    file_path = os.path.join(settings.MEDIA_ROOT, 'documentos', 'MANUAL DE USUARIO.pdf')
    if os.path.exists(file_path):
        with open(file_path, 'rb') as fh:
            response = HttpResponse(fh.read(), content_type="application/pdf")
            response['Content-Disposition'] = 'attachment; filename=' + os.path.basename(file_path)
            return response
    
    return HttpResponseNotFound('El Archivo solicitado no fue encontrado.')
