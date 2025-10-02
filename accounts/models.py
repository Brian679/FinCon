from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    USER_TYPE_CHOICES = (
        ('client', 'Client'),
        ('staff', 'Staff'),
        ('admin', 'Admin'),
    )
    
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES, default='client')
    phone = models.CharField(max_length=20, blank=True)
    company_name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.username} ({self.get_user_type_display()})"
    
    @property
    def is_client(self):
        return self.user_type == 'client'
    
    @property
    def is_staff_member(self):
        return self.user_type in ['staff', 'admin']
