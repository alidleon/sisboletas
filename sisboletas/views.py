from django.shortcuts import render

def main(request):
    return render(request, 'main.html')

def master(request):
    return render(request, 'index_master.html')

def index(request):
    return render(request, 'index.html')