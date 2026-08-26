from __future__ import annotations

from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
from django.http import FileResponse, Http404
from rest_framework import status
from rest_framework.decorators import (api_view,permission_classes,parser_classes,)
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response


from apps.cms.models import HeroSection

from apps.tickets.models import (
    Project,
    Product,
    Category,
    SupportGroup,
    DynamicForm,
    Ticket,
    TicketComment,
    TicketAttachment,
    TicketEvent,
    Notification,
    SLAPolicy,
)

from .permissions import visible_tickets_for_user


User = get_user_model()


# ============================================================
# HELPERS
# ============================================================

def absolute_file_url(request, file_field):
    """
    Convert Django FileField/ImageField into absolute URL.
    """

    if not file_field:
        return None

    try:
        return request.build_absolute_uri(file_field.url)
    except Exception:
        return None


def user_json(user):
    if not user:
        return None

    return {
        "id": user.pk,
        "email": getattr(user, "email", ""),
        "first_name": getattr(user, "first_name", ""),
        "last_name": getattr(user, "last_name", ""),
        "full_name": user.get_full_name() or getattr(user, "email", ""),
        "is_active": user.is_active,
        "is_staff": user.is_staff,
    }


def project_json(project):
    if not project:
        return None

    return {
        "id": project.pk,
        "code": getattr(project, "code", None),
        "name_en": getattr(project, "name_en", None),
        "name_ar": getattr(project, "name_ar", None),
        "is_active": getattr(project, "is_active", True),
    }


def product_json(product):
    if not product:
        return None

    return {
        "id": product.pk,
        "project_id": getattr(product, "project_id", None),
        "code": getattr(product, "code", None),
        "name_en": getattr(product, "name_en", None),
        "name_ar": getattr(product, "name_ar", None),
        "is_active": getattr(product, "is_active", True),
    }


def category_json(category):
    if not category:
        return None

    return {
        "id": category.pk,
        "product_id": getattr(category, "product_id", None),
        "code": getattr(category, "code", None),
        "name_en": getattr(category, "name_en", None),
        "name_ar": getattr(category, "name_ar", None),
        "default_priority": getattr(
            category,
            "default_priority",
            None,
        ),
        "is_active": getattr(category, "is_active", True),
    }


def support_group_json(group):
    return {
        "id": group.pk,
        "code": getattr(group, "code", None),
        "name": getattr(group, "name", None),
        "description": getattr(group, "description", None),
        "is_active": getattr(group, "is_active", True),
        "member_count": group.members.count()
        if hasattr(group, "members")
        else 0,
        "manager_count": group.managers.count()
        if hasattr(group, "managers")
        else 0,
    }


def ticket_list_json(ticket):
    return {
        "id": ticket.pk,
        "reference": getattr(ticket, "reference", None),
        "subject": getattr(ticket, "subject", None),
        "description": getattr(ticket, "description", None),

        "status": getattr(ticket, "status", None),
        "priority": getattr(ticket, "priority", None),

        "project": project_json(
            getattr(ticket, "project", None)
        ),

        "product": product_json(
            getattr(ticket, "product", None)
        ),

        "category": category_json(
            getattr(ticket, "category", None)
        ),

        "requester": user_json(
            getattr(ticket, "requester", None)
        ),

        "assignee": user_json(
            getattr(ticket, "assignee", None)
        ),

        "visibility": getattr(
            ticket,
            "visibility",
            None,
        ),

        "is_sensitive": getattr(
            ticket,
            "is_sensitive",
            False,
        ),

        "sla_state": getattr(
            ticket,
            "sla_state",
            None,
        ),

        "created_at": (
            ticket.created_at.isoformat()
            if getattr(ticket, "created_at", None)
            else None
        ),

        "updated_at": (
            ticket.updated_at.isoformat()
            if getattr(ticket, "updated_at", None)
            else None
        ),
    }


def comment_json(comment):
    return {
        "id": comment.pk,
        "ticket_id": comment.ticket_id,

        "author": user_json(
            getattr(comment, "author", None)
        ),

        "body": getattr(comment, "body", None),

        "is_internal": getattr(
            comment,
            "is_internal",
            False,
        ),

        "created_at": (
            comment.created_at.isoformat()
            if getattr(comment, "created_at", None)
            else None
        ),
    }


def attachment_json(request, attachment):
    file_field = getattr(
        attachment,
        "file",
        None,
    )

    return {
        "id": attachment.pk,
        "ticket_id": attachment.ticket_id,

        "original_name": getattr(
            attachment,
            "original_name",
            None,
        ),

        "content_type": getattr(
            attachment,
            "content_type",
            None,
        ),

        "size": getattr(
            attachment,
            "size",
            None,
        ),

        "file_url": absolute_file_url(
            request,
            file_field,
        ),

        "uploaded_by": user_json(
            getattr(
                attachment,
                "uploaded_by",
                None,
            )
        ),

        "created_at": (
            attachment.created_at.isoformat()
            if getattr(
                attachment,
                "created_at",
                None,
            )
            else None
        ),
    }


def event_json(event):
    return {
        "id": event.pk,
        "ticket_id": event.ticket_id,

        "event_type": getattr(
            event,
            "event_type",
            None,
        ),

        "description": getattr(
            event,
            "description",
            None,
        ),

        "data": getattr(
            event,
            "data",
            None,
        ),

        "created_at": (
            event.created_at.isoformat()
            if getattr(event, "created_at", None)
            else None
        ),
    }


def get_ticket_or_404(request, ticket_id):
    queryset = (
        Ticket.objects
        .select_related(
            "requester",
            "assignee",
            "project",
            "product",
            "category",
        )
        .prefetch_related(
            "groups",
            "assignees",
        )
    )

    queryset = visible_tickets_for_user(
        queryset,
        request.user,
    )

    return queryset.filter(
        pk=ticket_id
    ).first()


def paginate_queryset(request, queryset):
    """
    Very simple pagination without DRF serializers.
    """

    try:
        page = max(
            int(request.GET.get("page", 1)),
            1,
        )
    except ValueError:
        page = 1

    try:
        page_size = int(
            request.GET.get(
                "page_size",
                25,
            )
        )
    except ValueError:
        page_size = 25

    page_size = min(
        max(page_size, 1),
        200,
    )

    total = queryset.count()

    start = (
        page - 1
    ) * page_size

    end = start + page_size

    return {
        "queryset": queryset[start:end],
        "page": page,
        "page_size": page_size,
        "count": total,
        "pages": (
            (total + page_size - 1)
            // page_size
        ),
    }


# ============================================================
# HEALTH
# ============================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def health(request):

    return Response({
        "success": True,
        "service": "GLIS Enterprise Platform API",
        "version": "1.0.0",
        "status": "healthy",
        "timestamp": timezone.now(),
    })


# ============================================================
# CURRENT USER
# ============================================================

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def current_user(request):

    user = request.user

    if request.method == "PATCH":

        allowed_fields = (
            "first_name",
            "last_name",
        )

        changed = []

        for field in allowed_fields:

            if field in request.data:

                setattr(
                    user,
                    field,
                    request.data[field],
                )

                changed.append(field)

        if changed:
            user.save(
                update_fields=changed
            )

    data = user_json(user)
    data["groups"] = list(user.groups.values("id","name",))
    profile = getattr(user,"profile",None,)
    data["role"] = (
        getattr(
            profile,
            "role",
            None,
        )
        if profile
        else None
    )

    return Response({
        "success": True,
        "data": data,
    })


# ============================================================
# USERS
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def users(request):

    query = (
        request.GET
        .get(
            "search",
            "",
        )
        .strip()
    )

    if request.user.is_staff:

        queryset = User.objects.filter(
            is_active=True
        )

    else:

        queryset = User.objects.filter(
            pk=request.user.pk
        )

    if query:

        queryset = queryset.filter(
            Q(email__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
        )

    queryset = queryset.order_by(
        "first_name",
        "last_name",
    )

    data = [
        user_json(user)
        for user in queryset
    ]

    return Response({
        "success": True,
        "data": data,
    })


# ============================================================
# PROJECTS
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def projects(request):

    if request.method == "GET":

        queryset = Project.objects.all()

        if not request.user.is_staff:
            queryset = queryset.filter(
                is_active=True
            )

        search = (
            request.GET
            .get(
                "search",
                "",
            )
            .strip()
        )

        if search:

            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name_en__icontains=search)
                | Q(name_ar__icontains=search)
            )

        data = [
            project_json(obj)
            for obj in queryset.order_by(
                "name_en"
            )
        ]

        return Response({
            "success": True,
            "data": data,
        })

    # POST
    if not request.user.is_staff:

        return Response(
            {
                "success": False,
                "detail":
                    "Administrator access required.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    code = request.data.get("code")
    name_en = request.data.get("name_en")

    if not code or not name_en:

        return Response(
            {
                "success": False,
                "detail":
                    "code and name_en are required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    project = Project.objects.create(
        code=code,
        name_en=name_en,
        name_ar=request.data.get(
            "name_ar",
            "",
        ),
        is_active=request.data.get(
            "is_active",
            True,
        ),
    )

    return Response(
        {
            "success": True,
            "data": project_json(project),
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(
    [
        "GET",
        "PATCH",
        "DELETE",
    ]
)
@permission_classes([IsAuthenticated])
def project_detail(request, project_id):

    project = Project.objects.filter(
        pk=project_id
    ).first()

    if not project:

        return Response(
            {
                "success": False,
                "detail": "Project not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":

        return Response({
            "success": True,
            "data": project_json(project),
        })

    if not request.user.is_staff:

        return Response(
            {
                "success": False,
                "detail":
                    "Administrator access required.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if request.method == "DELETE":

        project.delete()

        return Response({
            "success": True,
        })

    fields = (
        "code",
        "name_en",
        "name_ar",
        "is_active",
    )

    changed = []

    for field in fields:

        if field in request.data:

            setattr(
                project,
                field,
                request.data[field],
            )

            changed.append(field)

    if changed:
        project.save(
            update_fields=changed
        )

    return Response({
        "success": True,
        "data": project_json(project),
    })


# ============================================================
# PRODUCTS
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def products(request):

    if request.method == "GET":

        queryset = (
            Product.objects
            .select_related("project")
        )

        if not request.user.is_staff:
            queryset = queryset.filter(
                is_active=True
            )

        project_id = request.GET.get(
            "project"
        )

        if project_id:
            queryset = queryset.filter(
                project_id=project_id
            )

        search = (
            request.GET
            .get(
                "search",
                "",
            )
            .strip()
        )

        if search:

            queryset = queryset.filter(
                Q(code__icontains=search)
                | Q(name_en__icontains=search)
                | Q(name_ar__icontains=search)
            )

        return Response({
            "success": True,
            "data": [
                product_json(obj)
                for obj
                in queryset.order_by(
                    "name_en"
                )
            ],
        })

    if not request.user.is_staff:

        return Response(
            {
                "success": False,
                "detail":
                    "Administrator access required.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    project_id = request.data.get(
        "project"
    )

    code = request.data.get("code")

    name_en = request.data.get(
        "name_en"
    )

    if not all(
        [
            project_id,
            code,
            name_en,
        ]
    ):

        return Response(
            {
                "success": False,
                "detail":
                    "project, code and name_en are required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    project = Project.objects.filter(
        pk=project_id
    ).first()

    if not project:

        return Response(
            {
                "success": False,
                "detail": "Invalid project.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    product = Product.objects.create(
        project=project,
        code=code,
        name_en=name_en,
        name_ar=request.data.get(
            "name_ar",
            "",
        ),
        is_active=request.data.get(
            "is_active",
            True,
        ),
    )

    return Response(
        {
            "success": True,
            "data": product_json(product),
        },
        status=status.HTTP_201_CREATED,
    )


# ============================================================
# CATEGORIES
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def categories(request):

    if request.method == "GET":

        queryset = (
            Category.objects
            .select_related(
                "product",
                "product__project",
            )
        )

        if not request.user.is_staff:
            queryset = queryset.filter(
                is_active=True
            )

        product_id = request.GET.get(
            "product"
        )

        project_id = request.GET.get(
            "project"
        )

        if product_id:
            queryset = queryset.filter(
                product_id=product_id
            )

        if project_id:
            queryset = queryset.filter(
                product__project_id=project_id
            )

        return Response({
            "success": True,
            "data": [
                category_json(obj)
                for obj
                in queryset.order_by(
                    "name_en"
                )
            ],
        })

    if not request.user.is_staff:

        return Response(
            {
                "success": False,
                "detail":
                    "Administrator access required.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    product_id = request.data.get(
        "product"
    )

    code = request.data.get("code")

    name_en = request.data.get(
        "name_en"
    )

    if not all(
        [
            product_id,
            code,
            name_en,
        ]
    ):

        return Response(
            {
                "success": False,
                "detail":
                    "product, code and name_en are required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    product = Product.objects.filter(
        pk=product_id
    ).first()

    if not product:

        return Response(
            {
                "success": False,
                "detail": "Invalid product.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    values = {
        "product": product,
        "code": code,
        "name_en": name_en,
        "name_ar": request.data.get(
            "name_ar",
            "",
        ),
        "is_active": request.data.get(
            "is_active",
            True,
        ),
    }

    if hasattr(
        Category,
        "default_priority",
    ):
        values["default_priority"] = (
            request.data.get(
                "default_priority"
            )
        )

    category = Category.objects.create(
        **values
    )

    return Response(
        {
            "success": True,
            "data":
                category_json(category),
        },
        status=status.HTTP_201_CREATED,
    )


# ============================================================
# SUPPORT GROUPS
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def support_groups(request):

    queryset = SupportGroup.objects.all()

    if not request.user.is_staff:

        queryset = queryset.filter(
            Q(members=request.user)
            | Q(managers=request.user)
        )

    if hasattr(
        SupportGroup,
        "is_active",
    ):
        queryset = queryset.filter(
            is_active=True
        )

    queryset = queryset.distinct()

    return Response({
        "success": True,
        "data": [
            support_group_json(obj)
            for obj in queryset
        ],
    })


# ============================================================
# HERO SECTION
# ============================================================

@api_view(["GET"])
@permission_classes([AllowAny])
def hero_sections(request):
    queryset = HeroSection.objects.all()
    if hasattr(HeroSection,"is_active",):
        queryset = queryset.filter(is_active=True)
    data = []
    for hero in queryset:
        data.append({
            "id": hero.pk,
            "hero_image": absolute_file_url(
                request,
                getattr(
                    hero,
                    "hero_image",
                    None,
                ),
            ),
        })

    return Response({
        "success": True,
        "data": data,
    })


@api_view(["GET"])
@permission_classes([AllowAny])
def hero_image(request, pk):
    try:
        hero = HeroSection.objects.get(pk=pk)
    except HeroSection.DoesNotExist:
        raise Http404("Hero section not found")
    if not hero.hero_image:
        raise Http404("Hero image not found")
    return FileResponse(hero.hero_image.open("rb"),content_type="image/jpeg",)

# ============================================================
# DYNAMIC FORMS
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dynamic_forms(request):

    queryset = DynamicForm.objects.all()

    if hasattr(
        DynamicForm,
        "active_version",
    ):

        queryset = queryset.select_related(
            "active_version"
        )

    if hasattr(
        DynamicForm,
        "is_active",
    ):
        queryset = queryset.filter(
            is_active=True
        )

    data = []

    for form in queryset:

        version = getattr(
            form,
            "active_version",
            None,
        )

        data.append({
            "id": form.pk,
            "key": getattr(
                form,
                "key",
                None,
            ),

            "name_en": getattr(
                form,
                "name_en",
                None,
            ),

            "name_ar": getattr(
                form,
                "name_ar",
                None,
            ),

            "project_id": getattr(
                form,
                "project_id",
                None,
            ),

            "product_id": getattr(
                form,
                "product_id",
                None,
            ),

            "category_id": getattr(
                form,
                "category_id",
                None,
            ),

            "active_version": (
                getattr(
                    version,
                    "version",
                    None,
                )
                if version
                else None
            ),
        })

    return Response({
        "success": True,
        "data": data,
    })


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dynamic_form_schema(
    request,
    form_key,
):

    form = DynamicForm.objects.filter(
        key=form_key
    ).first()

    if not form:

        return Response(
            {
                "success": False,
                "detail":
                    "Dynamic form not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    version = getattr(
        form,
        "active_version",
        None,
    )

    if not version:

        return Response(
            {
                "success": False,
                "detail":
                    "No active form version configured.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({
        "success": True,

        "data": {
            "form_id": form.pk,
            "form_key": form.key,

            "version": getattr(
                version,
                "version",
                None,
            ),

            "schema": getattr(
                version,
                "schema",
                {},
            ),
        },
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def dynamic_form_validate(
    request,
    form_key,
):

    form = DynamicForm.objects.filter(
        key=form_key
    ).first()

    if not form:

        return Response(
            {
                "success": False,
                "detail":
                    "Dynamic form not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    version = getattr(
        form,
        "active_version",
        None,
    )

    if not version:

        return Response(
            {
                "success": False,
                "detail":
                    "No active version.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    schema = getattr(
        version,
        "schema",
        {},
    ) or {}

    submitted = request.data.get(
        "data",
        request.data,
    )

    errors = {}

    for field in schema.get(
        "fields",
        [],
    ):

        name = field.get("name")

        if not name:
            continue

        if (
            field.get("required")
            and submitted.get(name)
            in (
                None,
                "",
                [],
            )
        ):

            errors[name] = (
                field.get("label_en")
                or name
            ) + " is required."

    return Response({
        "success": not bool(errors),
        "valid": not bool(errors),
        "errors": errors,
    })


# ============================================================
# TICKET LIST / CREATE
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def tickets(request):

    if request.method == "GET":

        queryset = (
            Ticket.objects
            .select_related(
                "requester",
                "assignee",
                "project",
                "product",
                "category",
            )
            .prefetch_related(
                "groups",
                "assignees",
            )
        )

        queryset = visible_tickets_for_user(
            queryset,
            request.user,
        )

        # ----------------------------------------------
        # filters
        # ----------------------------------------------

        status_value = request.GET.get(
            "status"
        )

        priority = request.GET.get(
            "priority"
        )

        project_id = request.GET.get(
            "project"
        )

        product_id = request.GET.get(
            "product"
        )

        category_id = request.GET.get(
            "category"
        )

        if status_value:
            queryset = queryset.filter(
                status=status_value
            )

        if priority:
            queryset = queryset.filter(
                priority=priority
            )

        if project_id:
            queryset = queryset.filter(
                project_id=project_id
            )

        if product_id:
            queryset = queryset.filter(
                product_id=product_id
            )

        if category_id:
            queryset = queryset.filter(
                category_id=category_id
            )

        if request.GET.get(
            "mine"
        ) in (
            "1",
            "true",
            "True",
        ):

            queryset = queryset.filter(
                requester=request.user
            )

        if request.GET.get(
            "assigned_to_me"
        ) in (
            "1",
            "true",
            "True",
        ):

            queryset = queryset.filter(
                Q(
                    assignee=request.user
                )
                | Q(
                    assignees=request.user
                )
            ).distinct()

        search = (
            request.GET
            .get(
                "search",
                "",
            )
            .strip()
        )

        if search:

            queryset = queryset.filter(
                Q(
                    reference__icontains=
                    search
                )
                | Q(
                    subject__icontains=
                    search
                )
                | Q(
                    description__icontains=
                    search
                )
            )

        queryset = queryset.order_by(
            "-created_at"
        )

        pagination = paginate_queryset(
            request,
            queryset,
        )

        return Response({
            "success": True,

            "pagination": {
                "count":
                    pagination["count"],

                "page":
                    pagination["page"],

                "page_size":
                    pagination[
                        "page_size"
                    ],

                "pages":
                    pagination["pages"],
            },

            "data": [
                ticket_list_json(obj)
                for obj
                in pagination["queryset"]
            ],
        })

    # ========================================================
    # CREATE TICKET
    # ========================================================

    subject = (
        request.data.get(
            "subject",
            "",
        )
        .strip()
    )

    description = (
        request.data.get(
            "description",
            "",
        )
        .strip()
    )

    project_id = request.data.get(
        "project"
    )

    product_id = request.data.get(
        "product"
    )

    category_id = request.data.get(
        "category"
    )

    if not subject:

        return Response(
            {
                "success": False,
                "detail":
                    "subject is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    project = None
    product = None
    category = None

    if project_id:

        project = Project.objects.filter(
            pk=project_id
        ).first()

        if not project:

            return Response(
                {
                    "success": False,
                    "detail":
                        "Invalid project.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    if product_id:

        product = Product.objects.filter(
            pk=product_id
        ).first()

        if not product:

            return Response(
                {
                    "success": False,
                    "detail":
                        "Invalid product.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            project
            and product.project_id
            != project.pk
        ):

            return Response(
                {
                    "success": False,
                    "detail":
                        "Product does not belong to selected project.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    if category_id:

        category = Category.objects.filter(
            pk=category_id
        ).first()

        if not category:

            return Response(
                {
                    "success": False,
                    "detail":
                        "Invalid category.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (
            product
            and category.product_id
            != product.pk
        ):

            return Response(
                {
                    "success": False,
                    "detail":
                        "Category does not belong to selected product.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    values = {
        "requester":
            request.user,

        "subject":
            subject,

        "description":
            description,

        "project":
            project,

        "product":
            product,

        "category":
            category,
    }

    optional_fields = (
        "priority",
        "visibility",
        "is_sensitive",
    )

    for field in optional_fields:

        if field in request.data:
            values[field] = (
                request.data[field]
            )

    with transaction.atomic():

        ticket = Ticket.objects.create(
            **values
        )

        group_ids = request.data.get(
            "groups"
        )

        if group_ids and hasattr(
            ticket,
            "groups",
        ):

            if not isinstance(
                group_ids,
                list,
            ):
                group_ids = [
                    group_ids
                ]

            ticket.groups.set(
                SupportGroup.objects.filter(
                    pk__in=group_ids
                )
            )

    return Response(
        {
            "success": True,
            "data":
                ticket_list_json(
                    ticket
                ),
        },
        status=status.HTTP_201_CREATED,
    )


# ============================================================
# TICKET DETAIL
# ============================================================

@api_view(
    [
        "GET",
        "PATCH",
        "DELETE",
    ]
)
@permission_classes([IsAuthenticated])
def ticket_detail(
    request,
    ticket_id,
):

    ticket = get_ticket_or_404(
        request,
        ticket_id,
    )

    if not ticket:

        return Response(
            {
                "success": False,
                "detail":
                    "Ticket not found or access denied.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "DELETE":

        if not request.user.is_staff:

            return Response(
                {
                    "success": False,
                    "detail":
                        "Administrator access required.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        ticket.delete()

        return Response({
            "success": True,
        })

    if request.method == "PATCH":

        editable_fields = (
            "subject",
            "description",
            "priority",
            "status",
            "visibility",
            "is_sensitive",
        )

        changed = []

        for field in editable_fields:

            if field in request.data:

                setattr(
                    ticket,
                    field,
                    request.data[field],
                )

                changed.append(field)

        if changed:

            ticket.save(
                update_fields=changed
                + (
                    ["updated_at"]
                    if hasattr(
                        ticket,
                        "updated_at",
                    )
                    else []
                )
            )

    data = ticket_list_json(
        ticket
    )

    comments_queryset = (
        TicketComment.objects
        .filter(ticket=ticket)
        .select_related("author")
        .order_by("created_at")
    )

    if not request.user.is_staff:

        if hasattr(
            TicketComment,
            "is_internal",
        ):
            comments_queryset = (
                comments_queryset
                .filter(
                    is_internal=False
                )
            )

    data["comments"] = [
        comment_json(comment)
        for comment
        in comments_queryset
    ]

    attachments_queryset = (
        TicketAttachment.objects
        .filter(ticket=ticket)
        .select_related(
            "uploaded_by"
        )
        .order_by("-created_at")
    )

    data["attachments"] = [
        attachment_json(
            request,
            attachment,
        )
        for attachment
        in attachments_queryset
    ]

    return Response({
        "success": True,
        "data": data,
    })


# ============================================================
# COMMENTS
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def ticket_comments(
    request,
    ticket_id,
):

    ticket = get_ticket_or_404(
        request,
        ticket_id,
    )

    if not ticket:

        return Response(
            {
                "success": False,
                "detail":
                    "Ticket not found or access denied.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    queryset = (
        TicketComment.objects
        .filter(ticket=ticket)
        .select_related("author")
        .order_by("created_at")
    )

    if request.method == "GET":

        if (
            not request.user.is_staff
            and hasattr(
                TicketComment,
                "is_internal",
            )
        ):

            queryset = queryset.filter(
                is_internal=False
            )

        return Response({
            "success": True,
            "data": [
                comment_json(obj)
                for obj in queryset
            ],
        })

    body = (
        request.data.get(
            "body",
            "",
        )
        .strip()
    )

    if not body:

        return Response(
            {
                "success": False,
                "detail":
                    "body is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    values = {
        "ticket": ticket,
        "author": request.user,
        "body": body,
    }

    if hasattr(
        TicketComment,
        "is_internal",
    ):

        is_internal = request.data.get(
            "is_internal",
            False,
        )

        # Normal customers cannot create
        # internal comments.
        if not request.user.is_staff:
            is_internal = False

        values["is_internal"] = (
            is_internal
        )

    comment = TicketComment.objects.create(
        **values
    )

    return Response(
        {
            "success": True,
            "data":
                comment_json(comment),
        },
        status=status.HTTP_201_CREATED,
    )


# ============================================================
# ATTACHMENTS
# ============================================================

@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
@parser_classes(
    [
        MultiPartParser,
        FormParser,
    ]
)
def ticket_attachments(
    request,
    ticket_id,
):

    ticket = get_ticket_or_404(
        request,
        ticket_id,
    )

    if not ticket:

        return Response(
            {
                "success": False,
                "detail":
                    "Ticket not found or access denied.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":

        queryset = (
            TicketAttachment.objects
            .filter(ticket=ticket)
            .select_related(
                "uploaded_by"
            )
            .order_by("-created_at")
        )

        return Response({
            "success": True,

            "data": [
                attachment_json(
                    request,
                    obj,
                )
                for obj in queryset
            ],
        })

    upload = request.FILES.get(
        "file"
    )

    if not upload:

        return Response(
            {
                "success": False,
                "detail":
                    "file is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 10 MB
    max_size = (
        10
        * 1024
        * 1024
    )

    if upload.size > max_size:

        return Response(
            {
                "success": False,
                "detail":
                    "Maximum file size is 10 MB.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    allowed_extensions = {
        ".pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
    }

    extension = (
        Path(
            upload.name
        )
        .suffix
        .lower()
    )

    if extension not in allowed_extensions:

        return Response(
            {
                "success": False,
                "detail":
                    "File type is not allowed.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    values = {
        "ticket": ticket,
        "uploaded_by":
            request.user,
    }

    # Find actual FileField name.
    file_field_name = None

    for field in (
        "file",
        "attachment",
        "document",
    ):

        try:
            TicketAttachment._meta.get_field(
                field
            )

            file_field_name = field

            break

        except Exception:
            pass

    if not file_field_name:

        return Response(
            {
                "success": False,
                "detail":
                    "TicketAttachment has no supported file field.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    values[
        file_field_name
    ] = upload

    for field_name, value in (
        (
            "original_name",
            upload.name,
        ),
        (
            "content_type",
            upload.content_type,
        ),
        (
            "size",
            upload.size,
        ),
    ):

        try:
            TicketAttachment._meta.get_field(
                field_name
            )
            values[field_name] = value

        except Exception:
            pass

    attachment = (
        TicketAttachment.objects.create(
            **values
        )
    )

    return Response(
        {
            "success": True,

            "data":
                attachment_json(
                    request,
                    attachment,
                ),
        },
        status=status.HTTP_201_CREATED,
    )


# ============================================================
# TICKET EVENTS
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def ticket_events(
    request,
    ticket_id,
):

    ticket = get_ticket_or_404(
        request,
        ticket_id,
    )

    if not ticket:

        return Response(
            {
                "success": False,
                "detail":
                    "Ticket not found or access denied.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    queryset = (
        TicketEvent.objects
        .filter(ticket=ticket)
        .order_by("-created_at")
    )

    return Response({
        "success": True,
        "data": [
            event_json(obj)
            for obj in queryset
        ],
    })


# ============================================================
# ASSIGN TICKET
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ticket_assign(
    request,
    ticket_id,
):

    ticket = get_ticket_or_404(
        request,
        ticket_id,
    )

    if not ticket:

        return Response(
            {
                "success": False,
                "detail":
                    "Ticket not found or access denied.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if not request.user.is_staff:

        permitted = False

        if hasattr(
            ticket,
            "groups",
        ):

            permitted = (
                ticket.groups
                .filter(
                    managers=request.user
                )
                .exists()
            )

        if not permitted:

            return Response(
                {
                    "success": False,
                    "detail":
                        "You cannot assign this ticket.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

    user_id = request.data.get(
        "user_id"
    )

    if not user_id:

        return Response(
            {
                "success": False,
                "detail":
                    "user_id is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    assignee = User.objects.filter(
        pk=user_id,
        is_active=True,
    ).first()

    if not assignee:

        return Response(
            {
                "success": False,
                "detail":
                    "User not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    ticket.assignee = assignee
    ticket.save()

    return Response({
        "success": True,

        "data": {
            "ticket_id":
                ticket.pk,

            "reference":
                ticket.reference,

            "assignee":
                user_json(assignee),
        },
    })


# ============================================================
# CHANGE STATUS
# ============================================================

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ticket_status(
    request,
    ticket_id,
):

    ticket = get_ticket_or_404(
        request,
        ticket_id,
    )

    if not ticket:

        return Response(
            {
                "success": False,
                "detail":
                    "Ticket not found or access denied.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    new_status = request.data.get(
        "status"
    )

    if not new_status:

        return Response(
            {
                "success": False,
                "detail":
                    "status is required.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    field = Ticket._meta.get_field(
        "status"
    )

    choices = getattr(
        field,
        "choices",
        [],
    )

    if choices:

        valid_values = [
            value
            for value, label
            in choices
        ]

        if new_status not in valid_values:

            return Response(
                {
                    "success": False,

                    "detail":
                        "Invalid status.",

                    "allowed":
                        valid_values,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

    ticket.status = new_status
    ticket.save()

    return Response({
        "success": True,
        "ticket_id": ticket.pk,
        "reference": ticket.reference,
        "status": ticket.status,
    })


# ============================================================
# NOTIFICATIONS
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notifications(request):

    queryset = (
        Notification.objects
        .filter(
            user=request.user
        )
        .order_by("-created_at")
    )

    data = []

    for notification in queryset:

        data.append({
            "id": notification.pk,

            "title": getattr(
                notification,
                "title",
                None,
            ),

            "message": getattr(
                notification,
                "message",
                None,
            ),

            "url": getattr(
                notification,
                "url",
                None,
            ),

            "is_read": bool(
                getattr(
                    notification,
                    "read_at",
                    None,
                )
            ),

            "read_at": (
                notification
                .read_at
                .isoformat()
                if getattr(
                    notification,
                    "read_at",
                    None,
                )
                else None
            ),

            "created_at": (
                notification
                .created_at
                .isoformat()
                if getattr(
                    notification,
                    "created_at",
                    None,
                )
                else None
            ),
        })

    return Response({
        "success": True,
        "data": data,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_read(
    request,
    notification_id,
):

    notification = (
        Notification.objects
        .filter(
            pk=notification_id,
            user=request.user,
        )
        .first()
    )

    if not notification:

        return Response(
            {
                "success": False,
                "detail":
                    "Notification not found.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if hasattr(
        notification,
        "read_at",
    ):

        notification.read_at = (
            timezone.now()
        )

        notification.save(
            update_fields=[
                "read_at"
            ]
        )

    return Response({
        "success": True,
    })


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notifications_read_all(request):

    updated = (
        Notification.objects
        .filter(
            user=request.user,
            read_at__isnull=True,
        )
        .update(
            read_at=timezone.now()
        )
    )

    return Response({
        "success": True,
        "updated": updated,
    })


# ============================================================
# SLA
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def sla_policies(request):

    queryset = SLAPolicy.objects.all()

    if hasattr(
        SLAPolicy,
        "is_active",
    ):
        queryset = queryset.filter(
            is_active=True
        )

    data = []

    for policy in queryset:

        item = {
            "id": policy.pk,
        }

        for field in (
            "name",
            "priority",
            "response_minutes",
            "resolution_minutes",
            "is_active",
        ):

            if hasattr(
                policy,
                field,
            ):

                item[field] = getattr(
                    policy,
                    field,
                )

        item["project_id"] = getattr(
            policy,
            "project_id",
            None,
        )

        item["category_id"] = getattr(
            policy,
            "category_id",
            None,
        )

        data.append(item)

    return Response({
        "success": True,
        "data": data,
    })


# ============================================================
# DASHBOARD
# ============================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):

    tickets_queryset = (
        visible_tickets_for_user(
            Ticket.objects.all(),
            request.user,
        )
    )

    total = tickets_queryset.count()

    mine = tickets_queryset.filter(
        requester=request.user
    ).count()

    assigned = (
        tickets_queryset
        .filter(
            Q(
                assignee=request.user
            )
            | Q(
                assignees=request.user
            )
        )
        .distinct()
        .count()
    )

    status_data = {}

    for row in (
        tickets_queryset
        .values("status")
        .annotate(
            total=Count("id")
        )
    ):

        status_data[
            row["status"]
        ] = row["total"]

    priority_data = {}

    for row in (
        tickets_queryset
        .values("priority")
        .annotate(
            total=Count("id")
        )
    ):

        priority_data[
            row["priority"]
        ] = row["total"]

    unread_notifications = (
        Notification.objects
        .filter(
            user=request.user,
            read_at__isnull=True,
        )
        .count()
    )

    recent = (
        tickets_queryset
        .select_related(
            "project",
            "product",
            "category",
            "requester",
            "assignee",
        )
        .order_by(
            "-created_at"
        )[:10]
    )

    return Response({
        "success": True,

        "data": {

            "kpis": {
                "total_tickets":
                    total,

                "my_tickets":
                    mine,

                "assigned_to_me":
                    assigned,

                "unread_notifications":
                    unread_notifications,
            },

            "status":
                status_data,

            "priority":
                priority_data,

            "recent_tickets": [
                ticket_list_json(obj)
                for obj in recent
            ],
        },
    })