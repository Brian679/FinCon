from django import forms
from .models import Document

ALLOWED_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png']
MAX_FILE_SIZE = 10 * 1024 * 1024

class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = ['document_type', 'title', 'file', 'description']
        widgets = {
            'document_type': forms.Select(attrs={'class': 'form-control'}),
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'file': forms.FileInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }
    
    def clean_file(self):
        file = self.cleaned_data.get('file')
        
        if file:
            import os
            ext = os.path.splitext(file.name)[1].lower()
            
            if ext not in ALLOWED_EXTENSIONS:
                raise forms.ValidationError(
                    f'File type not allowed. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'
                )
            
            if file.size > MAX_FILE_SIZE:
                raise forms.ValidationError(
                    f'File size exceeds maximum allowed size of {MAX_FILE_SIZE // (1024*1024)}MB'
                )
        
        return file
