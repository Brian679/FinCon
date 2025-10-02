from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect

def staff_required(function=None, redirect_url='dashboard'):
    actual_decorator = user_passes_test(
        lambda user: user.is_authenticated and user.is_staff_member,
        login_url=redirect_url
    )
    if function:
        return actual_decorator(function)
    return actual_decorator

def client_required(function=None, redirect_url='dashboard'):
    actual_decorator = user_passes_test(
        lambda user: user.is_authenticated and user.is_client,
        login_url=redirect_url
    )
    if function:
        return actual_decorator(function)
    return actual_decorator
