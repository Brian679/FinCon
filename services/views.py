from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from accounts.decorators import staff_required
from .models import ServiceCategory, Service, ServiceRequest

def home_view(request):
    categories = ServiceCategory.objects.all()
    featured_services = Service.objects.filter(is_active=True)[:6]
    context = {
        'categories': categories,
        'featured_services': featured_services,
    }
    return render(request, 'home.html', context)

def services_list_view(request):
    categories = ServiceCategory.objects.prefetch_related('services').all()
    context = {'categories': categories}
    return render(request, 'services/services_list.html', context)

def service_detail_view(request, slug):
    service = get_object_or_404(Service, slug=slug, is_active=True)
    context = {'service': service}
    return render(request, 'services/service_detail.html', context)

@login_required
def request_service_view(request, slug):
    service = get_object_or_404(Service, slug=slug, is_active=True)
    
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        service_request = ServiceRequest.objects.create(
            client=request.user,
            service=service,
            notes=notes
        )
        messages.success(request, f'Service request for {service.name} has been submitted successfully!')
        return redirect('dashboard')
    
    context = {'service': service}
    return render(request, 'services/request_service.html', context)

@staff_required
def staff_dashboard_view(request):
    pending_requests = ServiceRequest.objects.filter(status='pending')
    in_progress_requests = ServiceRequest.objects.filter(status='in_progress')
    
    context = {
        'pending_requests': pending_requests,
        'in_progress_requests': in_progress_requests,
    }
    return render(request, 'services/staff_dashboard.html', context)
