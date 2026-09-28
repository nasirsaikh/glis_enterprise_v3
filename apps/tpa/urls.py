from django.urls import path
from . import views
app_name="tpa"
urlpatterns=[
    path("",views.dashboard,name="dashboard"),
    path("transactions/",views.transaction_list,name="transaction_list"),
    path("transactions/new/",views.transaction_create,name="transaction_create"),
    path("transactions/<str:reference>/",views.transaction_detail,name="transaction_detail"),
    path("transactions/<str:reference>/submit/",views.transaction_submit,name="transaction_submit"),
]
