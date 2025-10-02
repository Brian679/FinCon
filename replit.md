# FinCon - Financial Consultancy Services Website

## Project Overview
FinCon is a comprehensive Django-based financial consultancy website featuring:
- User authentication with role-based access (clients vs staff)
- Service catalog with pricing for all financial consultancy offerings
- Document upload system with validation
- Appointment scheduling
- Invoice and payment tracking
- Client and staff dashboards
- Monochromatic design (black-to-white gradient theme)

## Recent Changes
- **October 2, 2025**: Initial project setup completed
  - Django 5.2.7 with PostgreSQL database
  - Custom user model with role-based access control
  - All service models (23 services across 8 categories) implemented
  - Homepage, service listings, and authentication pages created
  - Black-to-white gradient design theme applied throughout
  - Document upload with file validation (type and size checks)
  - Staff-only views protected with decorators

## Project Architecture

### Apps Structure
- **accounts**: User authentication, registration, profiles, role management
- **services**: Service catalog, categories, service requests
- **appointments**: Consultation scheduling system
- **documents**: Secure document upload and management
- **payments**: Invoice generation and payment tracking

### Database Models
- **User** (custom): username, email, user_type (client/staff/admin), company_name, phone, address
- **ServiceCategory**: name, slug, description, order
- **Service**: category, name, price, description, features
- **ServiceRequest**: client, service, status, assigned_to, notes
- **Appointment**: client, consultant, subject, appointment_date, status
- **Document**: uploaded_by, service_request, document_type, file (with validation)
- **Invoice**: client, service_request, amount, tax, total_amount, status
- **Payment**: invoice, amount, payment_method, transaction_id

### Services Offered
1. **Company Registration Services** ($60-110)
2. **Secretarial Services** ($25-30)
3. **Tax Consultancy Services** ($15-300)
4. **Procurement Services** ($120-140)
5. **NSSA Services** ($15-50)
6. **Additional Services** ($250-360)
7. **Accounting Services** ($350-500)
8. **Audit and Assurance** ($550-600)

## Technical Stack
- **Backend**: Django 5.2.7, Python 3.11
- **Database**: PostgreSQL (via DATABASE_URL environment variable)
- **Frontend**: Bootstrap 5, custom CSS with gradient design
- **Authentication**: Django built-in auth with custom User model
- **File Upload**: Django FileField with validation (max 10MB, allowed types: PDF, DOC, XLS, images)

## Security Features
- CSRF protection enabled
- Role-based access control with custom decorators (@staff_required, @client_required)
- File upload validation (file type and size restrictions)
- Secure password hashing
- Session-based authentication

## Environment Variables
- DATABASE_URL: PostgreSQL connection string (provided by Replit)
- SESSION_SECRET: Django secret key (provided by Replit)

## User Preferences
- Design: Black-to-white gradient theme (monochromatic)
- Branding: FinCon
- Tagline: "Need help with Accounting?"

## Development Workflow
- Server runs on port 5000 (required for Replit)
- Admin panel available at /admin/
- Debug mode enabled for development

## Next Phase Features
- Payment gateway integration (Stripe, Paynow, EcoCash, etc.)
- Live chat system
- Automated compliance checker for ZIMRA
- Email/SMS reminders for deadlines
- Analytics dashboard for clients
- Mobile app version
- Knowledge base and e-learning modules
