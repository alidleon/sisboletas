from django.shortcuts import render
from django.contrib.auth.decorators import login_required

def main(request):
    return render(request, 'main.html')

def master(request):
    return render(request, 'index_master.html')
@login_required
def index(request):
    context = {
        'mensaje_bienvenida': f"Bienvenido al Sistema, {request.user.username}!",
        
    }
    return render(request, 'index.html', context)