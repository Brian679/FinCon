import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fincon_project.settings')
django.setup()

from services.models import ServiceCategory, Service

categories_data = [
    {
        'name': 'Company Registration Services',
        'slug': 'company-registration',
        'description': 'Professional company registration and incorporation services',
        'order': 1,
        'services': [
            {'name': 'Private Limited Company', 'slug': 'private-limited-company', 'price': 110, 
             'description': 'Complete registration service for private limited companies', 
             'features': 'Full documentation\nZIMRA registration included\nCompliance check\nCertificate of incorporation'},
            {'name': 'Private Business Corporation', 'slug': 'private-business-corporation', 'price': 80,
             'description': 'Registration service for private business corporations',
             'features': 'Business name registration\nTax registration\nCompliance documentation\nBusiness certificate'},
            {'name': 'Company Re-Registration', 'slug': 'company-re-registration', 'price': 60,
             'description': 'Re-registration services for existing companies',
             'features': 'Documentation review\nUpdated certificates\nCompliance update\nZIMRA notification'},
        ]
    },
    {
        'name': 'Secretarial Services',
        'slug': 'secretarial-services',
        'description': 'Corporate secretarial and compliance services',
        'order': 2,
        'services': [
            {'name': 'Old Company Annual Returns', 'slug': 'old-company-annual-returns', 'price': 30,
             'description': 'Filing of annual returns for established companies',
             'features': 'Returns preparation\nFiling with registrar\nCompliance check\nConfirmation documentation'},
            {'name': 'Change of Director/Secretary', 'slug': 'change-director-secretary', 'price': 25,
             'description': 'Process changes in company directors or secretaries',
             'features': 'Form completion\nRegistrar filing\nUpdated documentation\nCompliance notification'},
            {'name': 'Annual Returns', 'slug': 'annual-returns', 'price': 25,
             'description': 'Standard annual returns filing service',
             'features': 'Returns preparation\nTimely filing\nRecord maintenance\nCompliance assurance'},
        ]
    },
    {
        'name': 'Tax Consultancy Services',
        'slug': 'tax-consultancy',
        'description': 'Comprehensive tax planning and compliance services',
        'order': 3,
        'services': [
            {'name': 'Tax Clearance (Companies)', 'slug': 'tax-clearance-companies', 'price': 30,
             'description': 'Tax clearance certificates for companies',
             'features': 'Application preparation\nZIMRA liaison\nClearance certificate\nCompliance verification'},
            {'name': 'Tax Clearance (Individual)', 'slug': 'tax-clearance-individual', 'price': 25,
             'description': 'Tax clearance certificates for individuals',
             'features': 'Personal tax review\nZIMRA application\nClearance certificate\nTax compliance check'},
            {'name': 'ZIMRA Registration', 'slug': 'zimra-registration', 'price': 15,
             'description': 'Registration with Zimbabwe Revenue Authority',
             'features': 'Registration forms\nTax number allocation\nCompliance setup\nConfirmation documentation'},
            {'name': 'VAT Registration', 'slug': 'vat-registration', 'price': 300,
             'description': 'Value Added Tax registration service',
             'features': 'VAT assessment\nRegistration application\nVAT number allocation\nCompliance training'},
            {'name': 'Tax Returns Submission', 'slug': 'tax-returns-submission', 'price': 20,
             'description': 'Professional tax returns filing service',
             'features': 'Returns preparation\nOnline submission\nConfirmation receipt\nRecord keeping'},
        ]
    },
    {
        'name': 'Procurement Services',
        'slug': 'procurement-services',
        'description': 'PRAZ registration and compliance services',
        'order': 4,
        'services': [
            {'name': 'PRAZ Registration', 'slug': 'praz-registration', 'price': 140,
             'description': 'Procurement Regulatory Authority registration',
             'features': 'Application preparation\nDocument compilation\nRegistration processing\nCertificate issuance'},
            {'name': 'PRAZ Certificate Renewal', 'slug': 'praz-renewal', 'price': 120,
             'description': 'Renewal of PRAZ registration certificates',
             'features': 'Renewal application\nCompliance check\nDocument update\nCertificate renewal'},
        ]
    },
    {
        'name': 'NSSA Services',
        'slug': 'nssa-services',
        'description': 'National Social Security Authority compliance services',
        'order': 5,
        'services': [
            {'name': 'NSSA Registration', 'slug': 'nssa-registration', 'price': 50,
             'description': 'Registration with National Social Security Authority',
             'features': 'Registration application\nEmployer setup\nEmployee registration\nContribution setup'},
            {'name': 'NSSA Compliance Certificate', 'slug': 'nssa-compliance', 'price': 30,
             'description': 'NSSA compliance certificate application',
             'features': 'Compliance review\nCertificate application\nNSSA liaison\nCertificate issuance'},
            {'name': 'P4 Form Submission', 'slug': 'p4-form-submission', 'price': 15,
             'description': 'Monthly P4 form submission service',
             'features': 'Form preparation\nOnline submission\nPayment processing\nConfirmation receipt'},
        ]
    },
    {
        'name': 'Additional Services',
        'slug': 'additional-services',
        'description': 'Specialized business and legal services',
        'order': 6,
        'services': [
            {'name': 'Trust Registration', 'slug': 'trust-registration', 'price': 360,
             'description': 'Complete trust registration and setup',
             'features': 'Trust deed preparation\nRegistration processing\nTrustee documentation\nCompliance setup'},
            {'name': 'Vendor Number', 'slug': 'vendor-number', 'price': 250,
             'description': 'Vendor number application and registration',
             'features': 'Application preparation\nDocument compilation\nRegistration processing\nVendor number allocation'},
        ]
    },
    {
        'name': 'Accounting Services',
        'slug': 'accounting-services',
        'description': 'Professional accounting services for educational institutions',
        'order': 7,
        'services': [
            {'name': 'Accounting for Private Colleges', 'slug': 'accounting-private-colleges', 'price': 500,
             'description': 'Comprehensive accounting services for private colleges',
             'features': 'Financial record management\nCompliance reporting\nZIMRA compliance\nFinancial statements'},
            {'name': 'Accounting for Schools', 'slug': 'accounting-schools', 'price': 400,
             'description': 'Accounting services for private schools',
             'features': 'School financial management\nBudget preparation\nFee management\nFinancial reporting'},
            {'name': 'Accounting for Centers', 'slug': 'accounting-centers', 'price': 350,
             'description': 'Accounting services for training and learning centers',
             'features': 'Financial bookkeeping\nExpense tracking\nRevenue management\nFinancial reports'},
        ]
    },
    {
        'name': 'Audit and Assurance',
        'slug': 'audit-assurance',
        'description': 'Professional audit services for government and council institutions',
        'order': 8,
        'services': [
            {'name': 'Government School Audit', 'slug': 'government-school-audit', 'price': 600,
             'description': 'Comprehensive audit services for government schools',
             'features': 'Financial audit\nCompliance check\nInternal controls review\nAudit report'},
            {'name': 'Council School Audit', 'slug': 'council-school-audit', 'price': 550,
             'description': 'Audit services for council-managed schools',
             'features': 'Financial statement audit\nCompliance verification\nRisk assessment\nDetailed audit report'},
        ]
    },
]

print("Starting database population...")

for cat_data in categories_data:
    category, created = ServiceCategory.objects.get_or_create(
        slug=cat_data['slug'],
        defaults={
            'name': cat_data['name'],
            'description': cat_data['description'],
            'order': cat_data['order']
        }
    )
    print(f"{'Created' if created else 'Updated'} category: {category.name}")
    
    for svc_data in cat_data['services']:
        service, created = Service.objects.get_or_create(
            slug=svc_data['slug'],
            defaults={
                'category': category,
                'name': svc_data['name'],
                'description': svc_data['description'],
                'price': svc_data['price'],
                'features': svc_data['features'],
                'is_active': True
            }
        )
        print(f"  {'Created' if created else 'Updated'} service: {service.name} - ${service.price}")

print("\nDatabase population complete!")
print(f"Total categories: {ServiceCategory.objects.count()}")
print(f"Total services: {Service.objects.count()}")
