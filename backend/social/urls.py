from django.urls import path

from . import views as v

app_name = "social"

urlpatterns = [
    path("wildlife/", v.WildlifeList.as_view(), name="wildlife_list"),
    path("wildlife/new/", v.WildlifeNew.as_view(), name="wildlife_new"),
    path("wildlife/<uuid:pk>/", v.WildlifeDetail.as_view(), name="wildlife"),
    path("wildlife/<uuid:pk>/edit/", v.WildlifeEdit.as_view(), name="wildlife_edit"),
    path("quotas/", v.QuotaList.as_view(), name="quotas"),
    path("quotas/new/", v.QuotaNew.as_view(), name="quota_new"),
    path("quotas/<uuid:pk>/", v.QuotaEdit.as_view(), name="quota_edit"),
    path("hunts/", v.HuntList.as_view(), name="hunts"),
    path("hunts/new/", v.hunt_new, name="hunt_new"),
    path("hunts/<uuid:pk>/", v.HuntDetail.as_view(), name="hunt"),
    path("hunts/<uuid:pk>/action/", v.hunt_action, name="hunt_action"),
    path("campfire/", v.campfire, name="campfire"),
    path("permits/", v.PermitList.as_view(), name="permits"),
    path("permits/new/", v.PermitNew.as_view(), name="permit_new"),
    path("permits/<uuid:pk>/", v.PermitDetail.as_view(), name="permit"),
    path("permits/<uuid:pk>/action/", v.permit_action, name="permit_action"),
    path("farms/", v.FarmList.as_view(), name="farms"),
    path("farms/new/", v.FarmNew.as_view(), name="farm_new"),
    path("farms/<uuid:pk>/", v.FarmDetail.as_view(), name="farm"),
    path("farms/<uuid:pk>/edit/", v.FarmEdit.as_view(), name="farm_edit"),
    path("water/", v.WaterList.as_view(), name="water_list"),
    path("water/new/", v.WaterNew.as_view(), name="water_new"),
    path("water/<uuid:pk>/", v.WaterDetail.as_view(), name="water"),
    path("water/<uuid:pk>/edit/", v.WaterEdit.as_view(), name="water_edit"),
    path("welfare/", v.BeneficiaryList.as_view(), name="beneficiaries"),
    path("welfare/new/", v.BeneficiaryNew.as_view(), name="beneficiary_new"),
    path("welfare/<uuid:pk>/", v.BeneficiaryDetail.as_view(), name="beneficiary"),
    path("welfare/<uuid:pk>/edit/", v.BeneficiaryEdit.as_view(), name="beneficiary_edit"),
    path("welfare/<uuid:pk>/action/", v.beneficiary_action, name="beneficiary_action"),
]
